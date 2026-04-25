import numpy as np
import pandas as pd
import pickle
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, r2_score, mean_squared_error
import xgboost as xgb
from rdkit import Chem
from rdkit.Chem import AllChem, Descriptors
from services.reaction_database import ReactionDatabase
from services.data_downloader import generate_synthetic_training_dataset
import asyncio
import json

logger = logging.getLogger(__name__)

# ── 12-category catalyst encoding ──
CATALYST_CATEGORIES = [
    'palladium', 'acid_bronsted', 'acid_lewis', 'base_organic',
    'base_inorganic', 'nickel', 'copper', 'ruthenium',
    'iron', 'enzyme', 'photocatalyst', 'none'
]

def classify_catalyst(catalyst_str: Optional[str]) -> str:
    """Classify a catalyst string into one of 12 categories."""
    if not catalyst_str:
        return 'none'
    c = catalyst_str.lower()
    if any(x in c for x in ['pd', 'palladium']):
        return 'palladium'
    if any(x in c for x in ['h2so4', 'hcl', 'tfa', 'p-ts']):
        return 'acid_bronsted'
    if any(x in c for x in ['alcl3', 'bf3', 'ticl4', 'zncl']):
        return 'acid_lewis'
    if any(x in c for x in ['et3n', 'dipea', 'dbu', 'dmap']):
        return 'base_organic'
    if any(x in c for x in ['k2co3', 'cs2co3', 'naoh', 'koh', 'nah']):
        return 'base_inorganic'
    if 'ni' in c:
        return 'nickel'
    if 'cu' in c:
        return 'copper'
    if 'ru' in c:
        return 'ruthenium'
    if 'fe' in c:
        return 'iron'
    if any(x in c for x in ['enzyme', 'lipase', 'esterase']):
        return 'enzyme'
    if any(x in c for x in ['ir(ppy)', 'ru(bpy)', 'eosin', 'photocatalyst']):
        return 'photocatalyst'
    return 'none'


class YieldPredictor:
    """ML-based yield prediction using XGBoost."""
    
    def __init__(self, model_path: Optional[str] = None):
        if model_path is None:
            # Better path resolution for Windows/Local environments
            base_dir = Path(__file__).parent.parent
            self.model_path = base_dir / "models" / "yield_model.pkl"
        else:
            self.model_path = Path(model_path)
        self.model = None
        self.feature_names = []
        self.scaler_params = {}
        self.model_params = {}
        self.model_metrics = {}
        self.model_version = "2.0.0"
        
    def compute_molecular_features(self, smiles: str) -> Dict[str, float]:
        """Compute molecular descriptors for a SMILES string."""
        try:
            mol = Chem.MolFromSmiles(smiles)
            if mol is None:
                return {}
            
            features = {
                'mol_weight': Descriptors.MolWt(mol),
                'logp': Descriptors.MolLogP(mol),
                'num_atoms': mol.GetNumAtoms(),
                'num_bonds': mol.GetNumBonds(),
                'num_rings': Descriptors.RingCount(mol),
                'num_aromatic_rings': Descriptors.NumAromaticRings(mol),
                'num_h_donors': Descriptors.NumHDonors(mol),
                'num_h_acceptors': Descriptors.NumHAcceptors(mol),
                'tpsa': Descriptors.TPSA(mol),
                'num_rotatable_bonds': Descriptors.NumRotatableBonds(mol),
                'num_heteroatoms': Descriptors.NumHeteroatoms(mol),
                'fraction_csp3': Descriptors.FractionCSP3(mol),
            }
            
            return features
        except Exception as e:
            logger.error(f"Error computing features for {smiles}: {str(e)}")
            return {}
    
    def compute_reaction_fingerprint(self, reactants: List[str], products: List[str]) -> np.ndarray:
        """Compute difference fingerprint for reaction."""
        try:
            # Compute fingerprints
            reactant_fps = []
            for smi in reactants:
                mol = Chem.MolFromSmiles(smi)
                if mol:
                    fp = AllChem.GetMorganFingerprintAsBitVect(mol, radius=2, nBits=512)
                    reactant_fps.append(np.array(fp))
            
            product_fps = []
            for smi in products:
                mol = Chem.MolFromSmiles(smi)
                if mol:
                    fp = AllChem.GetMorganFingerprintAsBitVect(mol, radius=2, nBits=512)
                    product_fps.append(np.array(fp))
            
            if not reactant_fps or not product_fps:
                return np.zeros(512)
            
            # Difference fingerprint (product - reactant)
            reactant_avg = np.mean(reactant_fps, axis=0)
            product_avg = np.mean(product_fps, axis=0)
            diff_fp = product_avg - reactant_avg
            
            return diff_fp
        except Exception as e:
            logger.error(f"Error computing reaction fingerprint: {str(e)}")
            return np.zeros(512)
    
    def featurize_reaction(self, reaction: Dict[str, Any]) -> Optional[np.ndarray]:
        """Convert reaction to feature vector."""
        try:
            features = []
            
            # Reaction fingerprint (512 dimensions)
            rxn_fp = self.compute_reaction_fingerprint(
                reaction.get('reactants', []),
                reaction.get('products', [])
            )
            features.extend(rxn_fp)
            
            # Molecular features of main reactant
            if reaction.get('reactants'):
                mol_features = self.compute_molecular_features(reaction['reactants'][0])
                features.extend([
                    mol_features.get('mol_weight', 0),
                    mol_features.get('logp', 0),
                    mol_features.get('num_atoms', 0),
                    mol_features.get('num_rings', 0),
                    mol_features.get('tpsa', 0),
                    mol_features.get('num_rotatable_bonds', 0),
                ])
            else:
                features.extend([0, 0, 0, 0, 0, 0])
            
            # Reaction conditions
            features.append(reaction.get('temperature_celsius', 25))
            
            # ── Catalyst: 12-category one-hot encoding ──
            catalyst_str = reaction.get('catalyst', '')
            catalyst_cat = classify_catalyst(catalyst_str)
            for cat in CATALYST_CATEGORIES:
                features.append(1 if cat == catalyst_cat else 0)
            
            # Solvent present flag
            features.append(1 if reaction.get('solvent') else 0)
            
            # Reaction type (one-hot encoding for common types)
            reaction_types = [
                'esterification', 'suzuki', 'reduction', 'oxidation',
                'amidation', 'sn2', 'aldol', 'diels-alder', 'grignard', 'friedel-crafts',
                'amide_coupling', 'wittig', 'reductive_amination',
                'buchwald_hartwig', 'heck', 'deprotection',
            ]
            rxn_type = reaction.get('reaction_type', '').lower()
            for rtype in reaction_types:
                features.append(1 if rtype in rxn_type else 0)
            
            return np.array(features)
            
        except Exception as e:
            logger.error(f"Error featurizing reaction: {str(e)}")
            return None
    
    async def prepare_training_data(self) -> List[Dict[str, Any]]:
        """Load training data from JSON file or generate synthetic data."""
        # Prefer local JSON file
        json_path = Path("training_reactions.json")
        if json_path.exists():
            with open(json_path, "r") as f:
                return json.load(f)
        
        # Fallback to fresh generation (now generates 3200+)
        return generate_synthetic_training_dataset(n_reactions=200)

    async def train(self, data: Optional[List[Dict[str, Any]]] = None, test_size: float = 0.2, random_state: int = 42) -> Dict[str, Any]:
        """Train the model using provided or prepared data."""
        if data is None:
            data = await self.prepare_training_data()
            
        if not data:
            logger.error("No training data available")
            return {}
        
        # Convert to features and labels
        X_list = []
        y_list = []
        for rxn in data:
            features = self.featurize_reaction(rxn)
            if features is not None:
                X_list.append(features)
                y_list.append(rxn.get('yield_percent', 0.0))
        
        if len(X_list) < 10:
            logger.warning(f"Insufficient data for training: {len(X_list)} samples")
            return {}
            
        X = np.array(X_list)
        y = np.array(y_list)

        # Split data
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=test_size, random_state=random_state
        )
        
        logger.info(f"Training set: {len(X_train)} samples")
        logger.info(f"Test set: {len(X_test)} samples")
        
        # ── Improved XGBoost parameters ──
        self.model = xgb.XGBRegressor(
            n_estimators=500,
            max_depth=7,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            min_child_weight=3,
            gamma=0.1,
            random_state=random_state,
            objective='reg:squarederror'
        )
        
        logger.info("Training XGBoost model (n_estimators=500, early_stopping=50)...")
        self.model.fit(
            X_train, y_train,
            eval_set=[(X_test, y_test)],
            verbose=False,
        )
        
        # Evaluate
        y_pred_train = self.model.predict(X_train)
        y_pred_test = self.model.predict(X_test)
        
        train_mae = mean_absolute_error(y_train, y_pred_train)
        test_mae = mean_absolute_error(y_test, y_pred_test)
        train_r2 = r2_score(y_train, y_pred_train)
        test_r2 = r2_score(y_test, y_pred_test)
        
        logger.info(f"Training MAE: {train_mae:.2f}%")
        logger.info(f"Test MAE: {test_mae:.2f}%")
        logger.info(f"Training R²: {train_r2:.3f}")
        logger.info(f"Test R²: {test_r2:.3f}")
        
        # Save model
        self.model_metrics = {
            'train_mae': float(train_mae),
            'test_mae': float(test_mae),
            'train_r2': float(train_r2),
            'test_r2': float(test_r2),
            'n_samples': int(len(X)),
            'n_features': int(X.shape[1]),
            'timestamp': datetime.utcnow().isoformat()
        }
        
        self.model_params = {
            'n_estimators': 500,
            'max_depth': 7,
            'learning_rate': 0.05,
            'subsample': 0.8,
            'colsample_bytree': 0.8,
            'min_child_weight': 3,
            'gamma': 0.1,
            'random_state': int(random_state)
        }
        
        self.save_model()
        
        return {
            'train_mae': float(train_mae),
            'test_mae': float(test_mae),
            'train_r2': float(train_r2),
            'test_r2': float(test_r2),
            'n_samples': len(X),
            'n_features': X.shape[1]
        }
    
    def predict(self, reaction: Dict[str, Any]) -> Optional[float]:
        """Predict yield for a reaction."""
        if self.model is None:
            self.load_model()
        
        if self.model is None:
            logger.warning("No trained model available")
            return None
        
        features = self.featurize_reaction(reaction)
        if features is None:
            return None
        
        prediction = self.model.predict(features.reshape(1, -1))[0]
        
        # Clip to realistic range
        prediction = max(0, min(100, prediction))
        
        return float(prediction)

    def predict_with_uncertainty(self, reaction: Dict[str, Any]) -> Dict[str, Any]:
        """
        Predict yield and attach uncertainty intervals (Legacy/Base version).
        
        Returns a dict compatible with SpecialistYieldPredictor.
        """
        point_estimate = self.predict(reaction)
        
        if point_estimate is None:
            return {
                "yield_percent": 75.0,
                "lower_bound": 50.0,
                "upper_bound": 95.0,
                "confidence_interval": 45.0,
                "confidence_level": "low",
                "model": "base_fallback"
            }
            
        # Default base uncertainty
        uncertainty = 15.0
        lower = max(0.0, point_estimate - uncertainty)
        upper = min(100.0, point_estimate + uncertainty)
        
        return {
            "yield_percent": round(point_estimate, 1),
            "lower_bound": round(lower, 1),
            "upper_bound": round(upper, 1),
            "confidence_interval": round(upper - lower, 1),
            "confidence_level": "medium",
            "model": "base_monolithic"
        }
    
    def save_model(self):
        """Save trained model to disk."""
        self.model_path.parent.mkdir(parents=True, exist_ok=True)
        
        model_data = {
            'model': self.model,
            'feature_names': self.feature_names,
            'scaler_params': self.scaler_params
        }
        
        with open(self.model_path, 'wb') as f:
            pickle.dump(model_data, f)
        
        # Also save human-readable metadata
        metadata_path = self.model_path.parent / "yield_model_metadata.json"
        metadata = {
            'version': self.model_version,
            'params': self.model_params,
            'metrics': self.model_metrics,
            'feature_names': self.feature_names
        }
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=4)
            
        logger.info(f"Model saved to {self.model_path} and metadata to {metadata_path}")
    
    def load_model(self):
        """Load trained model from disk."""
        if not self.model_path.exists():
            logger.warning(f"Model file not found: {self.model_path}")
            return False
        
        try:
            with open(self.model_path, 'rb') as f:
                model_data = pickle.load(f)
            
            self.model = model_data['model']
            self.feature_names = model_data.get('feature_names', [])
            self.scaler_params = model_data.get('scaler_params', {})
            
            logger.info(f"Model loaded from {self.model_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to load model: {str(e)}")
            return False


async def main():
    """Train the yield prediction model."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    predictor = YieldPredictor()
    metrics = await predictor.train()
    
    if metrics:
        print("\n" + "="*50)
        print("Yield Prediction Model Training Complete")
        print("="*50)
        print(f"Samples: {metrics['n_samples']}")
        print(f"Features: {metrics['n_features']}")
        print(f"Training MAE: {metrics['train_mae']:.2f}%")
        print(f"Test MAE: {metrics['test_mae']:.2f}%")
        print(f"Training R²: {metrics['train_r2']:.3f}")
        print(f"Test R²: {metrics['test_r2']:.3f}")
        print("="*50)

if __name__ == "__main__":
    asyncio.run(main())
