import numpy as np
import pandas as pd
import pickle
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, mean_absolute_error
from sklearn.preprocessing import LabelEncoder
import xgboost as xgb
from rdkit import Chem
from rdkit.Chem import AllChem, Descriptors
from services.reaction_database import ReactionDatabase
import asyncio

logger = logging.getLogger(__name__)


class SafeLabelEncoder:
    """Label encoder wrapper that maps unseen labels to index 0 ("unknown")."""

    def __init__(self, unknown_label: str = "unknown"):
        self.unknown_label = unknown_label
        self.encoder = LabelEncoder()
        self.classes_ = np.array([unknown_label], dtype=object)

    def fit(self, y):
        values = [self.unknown_label]
        values.extend([str(label) for label in y if str(label) != self.unknown_label])
        unique_values = sorted(set(values) - {self.unknown_label})
        ordered_classes = [self.unknown_label] + unique_values
        self.encoder.classes_ = np.array(ordered_classes, dtype=object)
        self.classes_ = self.encoder.classes_
        return self

    def transform(self, y):
        labels = [str(label) for label in y]
        try:
            return self.encoder.transform(labels)
        except ValueError:
            class_to_idx = {label: idx for idx, label in enumerate(self.classes_)}
            return np.array([class_to_idx.get(label, 0) for label in labels], dtype=int)

    def fit_transform(self, y):
        self.fit(y)
        return self.transform(y)

    def inverse_transform(self, y):
        return self.encoder.inverse_transform(y)


class ConditionPredictor:
    """ML-based prediction of optimal reaction conditions."""

    def __init__(self, model_dir: str = "/app/backend/models"):
        self.model_dir = Path(model_dir)
        self.model_dir.mkdir(parents=True, exist_ok=True)

        # Models for different condition types
        self.temp_model = None
        self.catalyst_model = None
        self.solvent_model = None

        # Label encoders
        self.catalyst_encoder = SafeLabelEncoder()
        self.solvent_encoder = SafeLabelEncoder()

        self.models_loaded = False

    def compute_reaction_features(self, reaction: Dict[str, Any]) -> np.ndarray:
        """Compute features for condition prediction."""
        try:
            features = []

            # Reaction fingerprint
            reactants = reaction.get('reactants', [])
            products = reaction.get('products', [])

            if not reactants or not products:
                return np.zeros(100)

            # Molecular features of main reactant
            try:
                mol = Chem.MolFromSmiles(reactants[0])
                if mol:
                    features.extend([
                        Descriptors.MolWt(mol),
                        Descriptors.MolLogP(mol),
                        mol.GetNumAtoms(),
                        Descriptors.RingCount(mol),
                        Descriptors.NumAromaticRings(mol),
                        Descriptors.NumHDonors(mol),
                        Descriptors.NumHAcceptors(mol),
                        Descriptors.TPSA(mol),
                        Descriptors.NumRotatableBonds(mol),
                        Descriptors.FractionCsp3(mol),
                    ])
                else:
                    features.extend([0] * 10)
            except:
                features.extend([0] * 10)

            # Product features
            try:
                mol = Chem.MolFromSmiles(products[0])
                if mol:
                    features.extend([
                        Descriptors.MolWt(mol),
                        Descriptors.MolLogP(mol),
                        mol.GetNumAtoms(),
                    ])
                else:
                    features.extend([0] * 3)
            except:
                features.extend([0] * 3)

            # Reaction type encoding
            reaction_types = [
                'esterification', 'suzuki', 'reduction', 'oxidation',
                'amidation', 'sn2', 'aldol', 'diels-alder', 'grignard', 'friedel-crafts'
            ]
            rxn_type = reaction.get('reaction_type', '').lower()
            for rtype in reaction_types:
                features.append(1 if rtype in rxn_type else 0)

            # Pad to fixed size
            while len(features) < 100:
                features.append(0)

            return np.array(features[:100])

        except Exception as e:
            logger.error(f"Error computing features: {str(e)}")
            return np.zeros(100)

    async def prepare_training_data(self) -> Tuple[np.ndarray, Dict[str, np.ndarray]]:
        """Load and prepare training data from database."""
        logger.info("Loading reactions for condition prediction...")

        db = ReactionDatabase()
        reactions = await db.get_reactions_with_yield(min_yield=0, limit=10000)

        logger.info(f"Loaded {len(reactions)} reactions")

        X = []
        y_temp = []
        y_catalyst = []
        y_solvent = []

        for rxn in reactions:
            features = self.compute_reaction_features(rxn)

            # Temperature target
            temp = rxn.get('temperature_celsius')
            if temp is not None:
                X.append(features)
                y_temp.append(temp)
                y_catalyst.append(rxn.get('catalyst', 'None'))
                y_solvent.append(rxn.get('solvent', 'None'))

        X = np.array(X)

        # Encode categorical targets
        y_catalyst_encoded = self.catalyst_encoder.fit_transform(y_catalyst)
        y_solvent_encoded = self.solvent_encoder.fit_transform(y_solvent)

        logger.info(f"Prepared {len(X)} samples")
        logger.info(f"Unique catalysts: {len(self.catalyst_encoder.classes_)}")
        logger.info(f"Unique solvents: {len(self.solvent_encoder.classes_)}")

        return X, {
            'temperature': np.array(y_temp),
            'catalyst': y_catalyst_encoded,
            'solvent': y_solvent_encoded
        }

    async def train(self, test_size: float = 0.2, random_state: int = 42):
        """Train condition prediction models."""
        logger.info("Starting condition prediction training...")

        # Prepare data
        X, y_dict = await self.prepare_training_data()

        if len(X) < 50:
            logger.warning(f"Insufficient data: {len(X)} samples")
            return None

        # Split data
        X_train, X_test, y_temp_train, y_temp_test = train_test_split(
            X, y_dict['temperature'], test_size=test_size, random_state=random_state
        )

        _, _, y_cat_train, y_cat_test = train_test_split(
            X, y_dict['catalyst'], test_size=test_size, random_state=random_state
        )

        _, _, y_solv_train, y_solv_test = train_test_split(
            X, y_dict['solvent'], test_size=test_size, random_state=random_state
        )

        metrics = {}

        # Train temperature model (regression)
        logger.info("Training temperature predictor...")
        self.temp_model = xgb.XGBRegressor(
            n_estimators=100,
            max_depth=5,
            learning_rate=0.1,
            random_state=random_state
        )
        self.temp_model.fit(X_train, y_temp_train)

        temp_pred = self.temp_model.predict(X_test)
        temp_mae = mean_absolute_error(y_temp_test, temp_pred)
        logger.info(f"Temperature MAE: {temp_mae:.2f}°C")
        metrics['temperature_mae'] = float(temp_mae)

        # Train catalyst model (classification)
        logger.info("Training catalyst predictor...")
        self.catalyst_model = xgb.XGBClassifier(
            n_estimators=100,
            max_depth=5,
            learning_rate=0.1,
            random_state=random_state
        )
        self.catalyst_model.fit(X_train, y_cat_train)

        cat_pred = self.catalyst_model.predict(X_test)
        cat_acc = accuracy_score(y_cat_test, cat_pred)
        logger.info(f"Catalyst accuracy: {cat_acc:.2%}")
        metrics['catalyst_accuracy'] = float(cat_acc)

        # Train solvent model (classification)
        logger.info("Training solvent predictor...")
        self.solvent_model = xgb.XGBClassifier(
            n_estimators=100,
            max_depth=5,
            learning_rate=0.1,
            random_state=random_state
        )
        self.solvent_model.fit(X_train, y_solv_train)

        solv_pred = self.solvent_model.predict(X_test)
        solv_acc = accuracy_score(y_solv_test, solv_pred)
        logger.info(f"Solvent accuracy: {solv_acc:.2%}")
        metrics['solvent_accuracy'] = float(solv_acc)

        # Save models
        self.save_models()

        metrics['n_samples'] = len(X)
        metrics['n_features'] = X.shape[1]

        return metrics

    def predict(self, reaction: Dict[str, Any]) -> Dict[str, Any]:
        """Predict optimal conditions for a reaction."""
        if not self.models_loaded:
            self.load_models()

        if not all([self.temp_model, self.catalyst_model, self.solvent_model]):
            # Use fallback values if models are not loaded
            return {
                "temperature_celsius": 25.0,
                "catalyst": "unknown",
                "solvent": "THF",
                "confidence": "low",
                "time_hours": 4.0,
                "fallback": True,
            }

        catalyst_hint = reaction.get('catalyst')
        solvent_hint = reaction.get('solvent')
        if catalyst_hint is not None:
            self.catalyst_encoder.transform([catalyst_hint])
        if solvent_hint is not None:
            self.solvent_encoder.transform([solvent_hint])

        features = self.compute_reaction_features(reaction).reshape(1, -1)

        # Predict temperature
        temp_pred = self.temp_model.predict(features)[0]
        temp_pred = max(-50, min(200, temp_pred))  # Reasonable range

        # Predict catalyst (with probabilities)
        cat_proba = self.catalyst_model.predict_proba(features)[0]
        cat_idx = np.argmax(cat_proba)
        catalyst = self.catalyst_encoder.inverse_transform([cat_idx])[0]
        cat_confidence = float(cat_proba[cat_idx])

        # Predict solvent (with probabilities)
        solv_proba = self.solvent_model.predict_proba(features)[0]
        solv_idx = np.argmax(solv_proba)
        solvent = self.solvent_encoder.inverse_transform([solv_idx])[0]
        solv_confidence = float(solv_proba[solv_idx])

        # Overall confidence
        confidence = 'high' if min(cat_confidence, solv_confidence) > 0.7 else                     'medium' if min(cat_confidence, solv_confidence) > 0.5 else 'low'

        return {
            'temperature_celsius': float(temp_pred),
            'catalyst': str(catalyst) if catalyst != 'None' else None,
            'solvent': str(solvent) if solvent != 'None' else None,
            'confidence': confidence,
            'catalyst_confidence': cat_confidence,
            'solvent_confidence': solv_confidence,
            'alternative_catalysts': self._get_alternatives(cat_proba, self.catalyst_encoder, top_k=3),
            'alternative_solvents': self._get_alternatives(solv_proba, self.solvent_encoder, top_k=3)
        }

    def predict_safe(self, reaction: Dict[str, Any]) -> Dict[str, Any]:
        """Safe prediction wrapper that returns fallback conditions when prediction fails."""
        try:
            return self.predict(reaction)
        except Exception as e:
            logger.error(f"Prediction failed; using fallback: {str(e)}")
            return {
                "temperature_celsius": 25.0,
                "catalyst": "unknown",
                "solvent": "THF",
                "confidence": 0.0,
                "fallback": True,
            }

    def predict_conditions(self, reaction: Dict[str, Any]) -> Dict[str, Any]:
        """Backward-compatible wrapper for existing callers."""
        return self.predict(reaction)

    def _get_alternatives(self, proba: np.ndarray, encoder: SafeLabelEncoder, top_k: int = 3) -> List[Dict]:
        """Get top alternative options with probabilities."""
        top_indices = np.argsort(proba)[-top_k:][::-1]
        alternatives = []

        for idx in top_indices:
            label = encoder.inverse_transform([idx])[0]
            if label != 'None':
                alternatives.append({
                    'option': str(label),
                    'confidence': float(proba[idx])
                })

        return alternatives

    def save_models(self):
        """Save all models to disk."""
        models_data = {
            'temp_model': self.temp_model,
            'catalyst_model': self.catalyst_model,
            'solvent_model': self.solvent_model,
            'catalyst_encoder': self.catalyst_encoder,
            'solvent_encoder': self.solvent_encoder
        }

        model_path = self.model_dir / 'condition_models.pkl'
        with open(model_path, 'wb') as f:
            pickle.dump(models_data, f)

        logger.info(f"Condition models saved to {model_path}")

    def load_models(self) -> bool:
        """Load models from disk."""
        model_path = self.model_dir / 'condition_models.pkl'

        if not model_path.exists():
            logger.warning(f"Model file not found: {model_path}")
            return False

        try:
            with open(model_path, 'rb') as f:
                models_data = pickle.load(f)

            self.temp_model = models_data['temp_model']
            self.catalyst_model = models_data['catalyst_model']
            self.solvent_model = models_data['solvent_model']
            self.catalyst_encoder = models_data['catalyst_encoder']
            self.solvent_encoder = models_data['solvent_encoder']

            self.models_loaded = True
            logger.info("Condition models loaded successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to load models: {str(e)}")
            return False


async def main():
    """Train condition prediction models."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    predictor = ConditionPredictor()
    metrics = await predictor.train()

    if metrics:
        print("\n" + "=" * 50)
        print("Condition Prediction Models Training Complete")
        print("=" * 50)
        print(f"Samples: {metrics['n_samples']}")
        print(f"Features: {metrics['n_features']}")
        print("\nTemperature Predictor:")
        print(f"  MAE: {metrics['temperature_mae']:.2f}°C")
        print("\nCatalyst Predictor:")
        print(f"  Accuracy: {metrics['catalyst_accuracy']:.2%}")
        print("\nSolvent Predictor:")
        print(f"  Accuracy: {metrics['solvent_accuracy']:.2%}")
        print("=" * 50)

        # Test prediction
        print("\nTesting prediction on sample reaction...")
        test_reaction = {
            'reactants': ['c1ccccc1', 'CC(=O)Cl'],
            'products': ['CC(=O)c1ccccc1'],
            'reaction_type': 'Friedel-Crafts acylation'
        }

        conditions = predictor.predict_safe(test_reaction)
        print("\nPredicted Conditions:")
        print(f"  Temperature: {conditions['temperature_celsius']:.1f}°C")
        print(f"  Catalyst: {conditions['catalyst']}")
        print(f"  Solvent: {conditions['solvent']}")
        print(f"  Confidence: {conditions['confidence']}")
        print("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())
