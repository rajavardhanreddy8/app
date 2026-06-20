import asyncio
import logging
import json
from pathlib import Path
from services.yield_predictor import QuantileYieldPredictor

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def main():
    """Train the quantile yield models."""
    logger.info("Starting Quantile Yield Model Training...")
    
    # Instantiate predictor
    predictor = QuantileYieldPredictor()
    
    # Load training data
    data_path = Path("training_reactions.json")
    if not data_path.exists():
        logger.error(f"Training data not found at {data_path}. Run generate_training_data.py first.")
        return

    with open(data_path, "r") as f:
        data = json.load(f)
    
    logger.info(f"Loaded {len(data)} reactions for training.")
    
    # Train
    metrics = await predictor.train(data=data)
    
    if metrics:
        logger.info("="*60)
        logger.info("QUANTILE MODEL TRAINING COMPLETE")
        logger.info("="*60)
        logger.info(f"Q50 MAE: {metrics['q50_mae']:.2f}%")
        logger.info(f"Samples: {metrics['n_samples']}")
        logger.info(f"Features: {metrics['n_features']}")
        logger.info(f"Saved to: {predictor.model_path}")
        logger.info("="*60)
    else:
        logger.error("Training failed.")

if __name__ == "__main__":
    asyncio.run(main())
