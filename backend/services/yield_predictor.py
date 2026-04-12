import numpy as np
import pandas as pd
import pickle
import logging
import json
from pathlib import Path
from typing import Dict, Any, Optional, List
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, r2_score, mean_squared_error
import xgboost as xgb
from rdkit import Chem
from rdkit.Chem import AllChem, Descriptors
from services.reaction_database import ReactionDatabase
import asyncio

logger = logging.getLogger(__name__)

class YieldPredictor:
    """ML-based yield prediction using XGBoost."""
    
    def __init__(self, model_path: str = "/app/backend/models/yield_model.pkl"):
        self.model_path = Path(model_path)
        self.model = None
        self.feature_names = []
        self.scaler_params = {}
        
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
                'fraction_csp3': Descriptors.FractionCsp3(mol),
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
            features.append(1 if reaction.get('catalyst') else 0)
            features.append(1 if reaction.get('solvent') else 0)
            
            # Reaction type (one-hot encoding for common types)
            reaction_types = [
                'esterification', 'suzuki', 'reduction', 'oxidation',
                'amidation', 'sn2', 'aldol', 'diels-alder', 'grignard', 'friedel-crafts'
            ]
            rxn_type = reaction.get('reaction_type', '').lower()
            for rtype in reaction_types:
                features.append(1 if rtype in rxn_type else 0)
            
            return np.array(features)
            
        except Exception as e:
            logger.error(f"Error featurizing reaction: {str(e)}")
            return None
    
    async def prepare_training_data(self) -> tuple:
        """Load reactions from local file + database and prepare training data."""
        training_path = Path(__file__).resolve().parents[1] / "data" / "training_reactions.json"
        file_reactions: List[Dict[str, Any]] = []
        db_reactions: List[Dict[str, Any]] = []

        if training_path.exists():
            try:
                with open(training_path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded, list):
                    file_reactions = loaded
                logger.info(f"Loaded {len(file_reactions)} reactions from {training_path}")
            except Exception as e:
                logger.warning(f"Failed to load training file {training_path}: {e}")

        try:
            logger.info("Loading reactions from database...")
            db = ReactionDatabase()
            db_reactions = await db.get_reactions_with_yield(min_yield=0, limit=10000)
            logger.info(f"Loaded {len(db_reactions)} reactions from MongoDB")
        except Exception as e:
            logger.warning(f"Failed to load reactions from MongoDB: {e}")

        reactions = file_reactions + db_reactions
        logger.info(
            f"Training data sources: file={len(file_reactions)}, mongo={len(db_reactions)}, combined={len(reactions)}"
        )
        
        X = []
        y = []
        
        for rxn in reactions:
            features = self.featurize_reaction(rxn)
            yield_value = rxn.get('yield_percent', rxn.get('yield'))
            if features is not None and yield_value is not None:
                X.append(features)
                y.append(float(yield_value))

        X = np.array(X)
        y = np.array(y)
        
        if len(X) == 0:
            logger.warning("No valid training samples found")
            return np.array([]), np.array([])

        logger.info(f"Prepared {len(X)} samples with {X.shape[1]} features")
        
        return X, y
    
    async def train(self, test_size: float = 0.2, random_state: int = 42):
        """Train the yield prediction model."""
        logger.info("Starting model training...")
        
        # Prepare data
        X, y = await self.prepare_training_data()
        
        if len(X) < 50:
            logger.warning(f"Insufficient data for training: {len(X)} samples")
            return None
        
        # Split data
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=test_size, random_state=random_state
        )
        
        logger.info(f"Training set: {len(X_train)} samples")
        logger.info(f"Test set: {len(X_test)} samples")
        
        # Train XGBoost model
        self.model = xgb.XGBRegressor(
            n_estimators=100,
            max_depth=6,
            learning_rate=0.1,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=random_state,
            objective='reg:squarederror'
        )
        
        logger.info("Training XGBoost model...")
        self.model.fit(X_train, y_train)
        
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
        
        logger.info(f"Model saved to {self.model_path}")
    
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
