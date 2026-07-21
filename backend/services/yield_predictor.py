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
from services.multi_model import MultiModelRegressor
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
    """ML-based yield prediction using multiple regression models."""
    
    def __init__(self, model_path: Optional[str] = None):
        if model_path is None:
            # Better path resolution for Windows/Local environments
            base_dir = Path(__file__).parent.parent
            self.model_path = base_dir / "models" / "yield_model.pkl"
        else:
            self.model_path = Path(model_path)
        self.multi_model_path = self.model_path.parent / "yield_model_multi.pkl"
        self.model = None
        self.multi_model = None
        self.feature_names = []
        self.scaler_params = {}
        self.model_params = {}
        self.model_metrics = {}
        self.model_version = "3.0.0"
        
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
        self.multi_model = MultiModelRegressor(random_state=random_state)
        model_metrics = self.multi_model.fit(X_train, y_train, X_test, y_test)

        if not self.multi_model.models:
            logger.error("No yield models trained successfully")
            return {}

        self.model = self.multi_model.get_best_model()
        ensemble_metrics = model_metrics.get("ensemble", {})
        train_mae = float(ensemble_metrics.get("train_mae", 0.0))
        test_mae = float(ensemble_metrics.get("test_mae", 0.0))
        train_r2 = float(ensemble_metrics.get("train_r2", 0.0))
        test_r2 = float(ensemble_metrics.get("test_r2", 0.0))

        logger.info(f"Best yield model: {self.multi_model.best_model_name}")
        logger.info(f"Ensemble Training MAE: {train_mae:.2f}%")
        logger.info(f"Ensemble Test MAE: {test_mae:.2f}%")
        logger.info(f"Ensemble Training R^2: {train_r2:.3f}")
        logger.info(f"Ensemble Test R^2: {test_r2:.3f}")

        self.model_metrics = {
            'train_mae': train_mae,
            'test_mae': test_mae,
            'train_r2': train_r2,
            'test_r2': test_r2,
            'n_samples': int(len(X)),
            'n_features': int(X.shape[1]),
            'timestamp': datetime.utcnow().isoformat(),
            'best_model': self.multi_model.best_model_name,
            'model_metrics': model_metrics,
            'skipped_models': self.multi_model.skipped_models,
        }

        self.model_params = {
            'candidate_models': list(self.multi_model.models.keys()),
            'best_model': self.multi_model.best_model_name,
            'random_state': int(random_state)
        }

        self.save_model()

        return {
            'train_mae': float(train_mae),
            'test_mae': float(test_mae),
            'train_r2': float(train_r2),
            'test_r2': float(test_r2),
            'n_samples': len(X),
            'n_features': X.shape[1],
            'best_model': self.multi_model.best_model_name,
            'model_metrics': model_metrics,
            'skipped_models': self.multi_model.skipped_models,
        }

        
        logger.info(f"Training R²: {train_r2:.3f}")
        logger.info(f"Test R²: {test_r2:.3f}")
        
    
    def predict(self, reaction: Dict[str, Any]) -> Optional[float]:
        """Predict yield for a reaction."""
        if self.multi_model is None and self.model is None:
            self.load_model()
        
        if self.multi_model is None and self.model is None:
            logger.warning("No trained model available")
            return None
        
        features = self.featurize_reaction(reaction)
        if features is None:
            return None
        
        if self.multi_model is not None:
            prediction = self.multi_model.predict(features.reshape(1, -1), clip_range=(0, 100))
        else:
            prediction = self.model.predict(features.reshape(1, -1))[0]

        if prediction is None:
            return None
        
        # Clip to realistic range
        prediction = max(0, min(100, prediction))
        
        return float(prediction)

    def predict_with_uncertainty(self, reaction: Dict[str, Any]) -> Dict[str, Any]:
        """
        Predict yield and attach uncertainty intervals.
        
        Attempts to use QuantileYieldPredictor for statistical bounds,
        falling back to a point estimate with ±15% heuristic.
        """
        # Try loading quantile models first
        quantile_predictor = QuantileYieldPredictor(fallback_predictor=self)
        if quantile_predictor.load_models():
            return quantile_predictor.predict_with_uncertainty(reaction)

        # Fallback to point estimate with heuristic
        point_estimate = self.predict(reaction)
        
        if point_estimate is None:
            return {
                "yield_percent": 75.0,
                "lower_bound": 50.0,
                "upper_bound": 95.0,
                "confidence_interval": 45.0,
                "confidence_level": "low",
                "model": "point_estimate_fallback"
            }
            
        # Default base uncertainty
        uncertainty = 15.0
        lower = float(np.clip(point_estimate - uncertainty, 0, 100))
        upper = float(np.clip(point_estimate + uncertainty, 0, 100))
        
        return {
            "yield_percent": round(point_estimate, 1),
            "lower_bound": round(lower, 1),
            "upper_bound": round(upper, 1),
            "confidence_interval": round(upper - lower, 1),
            "confidence_level": "medium",
            "model": "point_estimate_fallback"
        }
    
    def predict_with_uncertainty(self, reaction: Dict[str, Any]) -> Dict[str, Any]:
        """Predict yield with ensemble details and uncertainty bounds."""
        model_details = self._multi_model_prediction_details(reaction)
        point_estimate = (
            model_details.get("ensemble_prediction")
            if model_details.get("ensemble_prediction") is not None
            else self.predict(reaction)
        )

        quantile_predictor = QuantileYieldPredictor(fallback_predictor=self)
        if quantile_predictor.load_models():
            result = quantile_predictor.predict_with_uncertainty(reaction)
            if point_estimate is not None:
                return self._merge_uncertainty_with_model_details(
                    result,
                    point_estimate,
                    model_details,
                    bounds_model="quantile_xgboost",
                )
            return result

        if point_estimate is None:
            return {
                "yield_percent": 75.0,
                "lower_bound": 50.0,
                "upper_bound": 95.0,
                "confidence_interval": 45.0,
                "confidence_level": "low",
                "model": "point_estimate_fallback",
                "individual_predictions": {},
                "ensemble_prediction": None,
                "best_model": None,
                "model_metrics": {},
                "model_decision": "fallback",
            }

        disagreement = float(model_details.get("prediction_std") or 0.0)
        uncertainty = max(8.0, disagreement * 1.96) if model_details else 15.0
        lower = float(np.clip(point_estimate - uncertainty, 0, 100))
        upper = float(np.clip(point_estimate + uncertainty, 0, 100))
        ci = upper - lower
        confidence_level = "high" if ci < 15 else "medium" if ci < 25 else "low"

        result = {
            "yield_percent": round(float(point_estimate), 1),
            "lower_bound": round(lower, 1),
            "upper_bound": round(upper, 1),
            "confidence_interval": round(ci, 1),
            "confidence_level": confidence_level,
            "model": "multi_model_ensemble" if model_details else "point_estimate_fallback",
            "model_decision": "ensemble" if model_details else "fallback",
        }
        result.update(model_details)
        return result

    def _multi_model_prediction_details(self, reaction: Dict[str, Any]) -> Dict[str, Any]:
        if self.multi_model is None:
            self.load_model()
        if self.multi_model is None:
            return {}
        features = self.featurize_reaction(reaction)
        if features is None:
            return {}
        return self.multi_model.prediction_summary(features.reshape(1, -1), clip_range=(0, 100))

    def _merge_uncertainty_with_model_details(
        self,
        result: Dict[str, Any],
        point_estimate: float,
        model_details: Dict[str, Any],
        bounds_model: str,
    ) -> Dict[str, Any]:
        disagreement = float(model_details.get("prediction_std") or 0.0)
        spread = disagreement * 1.96
        lower = float(result.get("lower_bound", point_estimate))
        upper = float(result.get("upper_bound", point_estimate))
        if spread > 0:
            lower = min(lower, point_estimate - spread)
            upper = max(upper, point_estimate + spread)
        lower = float(np.clip(lower, 0, 100))
        upper = float(np.clip(upper, 0, 100))
        ci = upper - lower
        confidence = "high" if ci < 15 else "medium" if ci < 25 else "low"

        result.update({
            "yield_percent": round(float(point_estimate), 1),
            "lower_bound": round(lower, 1),
            "upper_bound": round(upper, 1),
            "confidence_interval": round(ci, 1),
            "confidence_level": confidence,
            "model": "multi_model_ensemble",
            "bounds_model": bounds_model,
            "model_decision": "ensemble",
        })
        result.setdefault("individual_predictions", {})
        result.setdefault("ensemble_prediction", round(float(point_estimate), 3))
        result.setdefault("best_model", None)
        result.setdefault("model_metrics", {})
        result.update(model_details)
        return result

    def save_model(self):
        """Save trained model to disk."""
        self.model_path.parent.mkdir(parents=True, exist_ok=True)
        
        model_data = {
            'model': self.model,
            'multi_model': self.multi_model,
            'feature_names': self.feature_names,
            'scaler_params': self.scaler_params,
            'model_metrics': self.model_metrics,
        }
        
        with open(self.model_path, 'wb') as f:
            pickle.dump(model_data, f)

        if self.multi_model is not None:
            multi_data = {
                'multi_model': self.multi_model,
                'feature_names': self.feature_names,
                'model_metrics': self.model_metrics,
                'version': self.model_version,
            }
            with open(self.multi_model_path, 'wb') as f:
                pickle.dump(multi_data, f)
        
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
        if self.multi_model_path.exists():
            try:
                with open(self.multi_model_path, 'rb') as f:
                    multi_data = pickle.load(f)
                self.multi_model = multi_data.get('multi_model', multi_data)
                self.model = (
                    self.multi_model.get_best_model()
                    if hasattr(self.multi_model, "get_best_model")
                    else None
                )
                self.feature_names = multi_data.get('feature_names', [])
                self.model_metrics = multi_data.get('model_metrics', {})
                logger.info(f"Multi-model yield bundle loaded from {self.multi_model_path}")
                return True
            except Exception as e:
                logger.error(f"Failed to load multi-model yield bundle: {str(e)}")

        if not self.model_path.exists():
            logger.warning(f"Model file not found: {self.model_path}")
            return False
        
        try:
            with open(self.model_path, 'rb') as f:
                model_data = pickle.load(f)
            
            self.model = model_data['model']
            self.multi_model = model_data.get('multi_model')
            self.feature_names = model_data.get('feature_names', [])
            self.scaler_params = model_data.get('scaler_params', {})
            self.model_metrics = model_data.get('model_metrics', {})
            
            logger.info(f"Model loaded from {self.model_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to load model: {str(e)}")
            return False


class QuantileYieldPredictor(YieldPredictor):
    """Yield predictor with q10/q50/q90 quantile uncertainty estimates."""

    def __init__(
        self,
        model_path: Optional[str] = None,
        fallback_predictor: Optional[YieldPredictor] = None,
    ):
        super().__init__(model_path=model_path)
        if model_path is None:
            base_dir = Path(__file__).parent.parent
            self.model_path = base_dir / "models" / "yield_model_quantile.pkl"
        
        self.q10_model = None
        self.q50_model = None
        self.q90_model = None
        self.fallback_predictor = fallback_predictor or YieldPredictor()

    async def train(self, data: Optional[List[Dict]] = None, test_size: float = 0.2, random_state: int = 42):
        """Train q10/q50/q90 models using quantile regression objective."""
        if data is None:
            data = await self.prepare_training_data()

        X_list, y_list = [], []
        for rxn in data:
            feat = self.featurize_reaction(rxn)
            if feat is not None:
                X_list.append(feat)
                y_list.append(rxn.get("yield_percent", 0.0))

        if len(X_list) < 50:
            logger.warning(f"Insufficient data for quantile training: {len(X_list)} samples")
            return None

        X = np.array(X_list)
        y = np.array(y_list)

        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=test_size, random_state=random_state
        )

        def _make_model(alpha: float):
            return xgb.XGBRegressor(
                objective="reg:quantileerror",
                quantile_alpha=alpha,
                n_estimators=500,
                max_depth=7,
                learning_rate=0.05,
                subsample=0.8,
                colsample_bytree=0.8,
                random_state=random_state,
            )

        self.q10_model = _make_model(0.10)
        self.q50_model = _make_model(0.50)
        self.q90_model = _make_model(0.90)

        logger.info(f"Training quantile models (alpha=0.1, 0.5, 0.9) on {len(X_train)} samples...")
        self.q10_model.fit(X_train, y_train)
        self.q50_model.fit(X_train, y_train)
        self.q90_model.fit(X_train, y_train)

        y_pred_q50 = np.clip(self.q50_model.predict(X_test), 0, 100)
        q50_mae = mean_absolute_error(y_test, y_pred_q50)

        self.save_models()
        return {
            "q50_mae": float(q50_mae),
            "n_samples": len(X),
            "n_features": X.shape[1],
        }

    def save_models(self):
        """Save quantile models."""
        self.model_path.parent.mkdir(parents=True, exist_ok=True)
        model_data = {
            "q10_model": self.q10_model,
            "q50_model": self.q50_model,
            "q90_model": self.q90_model,
        }
        with open(self.model_path, "wb") as f:
            pickle.dump(model_data, f)
        logger.info(f"Quantile models saved to {self.model_path}")

    def load_models(self) -> bool:
        """Load quantile models from yield_model_quantile.pkl."""
        if not self.model_path.exists():
            return False
        try:
            with open(self.model_path, "rb") as f:
                model_data = pickle.load(f)
            self.q10_model = model_data.get("q10_model")
            self.q50_model = model_data.get("q50_model")
            self.q90_model = model_data.get("q90_model")
            return all([self.q10_model, self.q50_model, self.q90_model])
        except Exception as e:
            logger.error(f"Failed to load quantile models: {e}")
            return False

    def predict_with_uncertainty(self, reaction: Dict[str, Any]) -> Dict[str, Any]:
        """Predict median yield and 10/90 quantile uncertainty bounds."""
        if not all([self.q10_model, self.q50_model, self.q90_model]) and not self.load_models():
            return self.fallback_predictor.predict_with_uncertainty(reaction)

        features = self.featurize_reaction(reaction)
        if features is None:
            return self.fallback_predictor.predict_with_uncertainty(reaction)

        x = features.reshape(1, -1)
        q10 = float(np.clip(self.q10_model.predict(x)[0], 0, 100))
        q50 = float(np.clip(self.q50_model.predict(x)[0], 0, 100))
        q90 = float(np.clip(self.q90_model.predict(x)[0], 0, 100))

        # Enforce lower_bound <= yield_percent <= upper_bound
        lower = min(q10, q50, q90)
        upper = max(q10, q50, q90)
        median = float(np.clip(q50, lower, upper))
        ci = upper - lower
        confidence = "high" if ci < 15 else "medium" if ci < 25 else "low"

        return {
            "yield_percent": round(median, 1),
            "lower_bound": round(lower, 1),
            "upper_bound": round(upper, 1),
            "confidence_interval": round(ci, 1),
            "confidence_level": confidence,
            "model": "quantile_xgboost",
        }


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
