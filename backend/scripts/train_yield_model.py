import asyncio
import logging
import sys
import os

# Add parent directory to sys.path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.yield_predictor import YieldPredictor

async def main():
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    
    logger.info("Starting yield model training script...")
    
    predictor = YieldPredictor(model_path="backend/models/yield_model.pkl")
    
    # Check if training reactions exist
    json_path = "backend/data/training_reactions.json"
    if not os.path.exists(json_path):
        logger.error(f"Training data not found at {json_path}. Please run generate_training_data.py first.")
        sys.exit(1)
        
    with open(json_path, "r") as f:
        import json
        data = json.load(f)
        
    logger.info(f"Loaded {len(data)} training reactions.")
    
    metrics = await predictor.train(data=data)
    
    if metrics:
        logger.info("Training complete!")
        logger.info(f"Final Metrics: {metrics}")
        predictor.save_model()
        logger.info("Model saved successfully.")
    else:
        logger.error("Training failed.")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
