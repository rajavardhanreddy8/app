import asyncio
import logging
import sys
import os
import json

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
        data = json.load(f)
        
    logger.info(f"Loaded {len(data)} training reactions.")
    
    metrics = await predictor.train(data=data)
    
    if metrics:
        logger.info("Training complete!")
        logger.info(f"Final Metrics: {metrics}")
        predictor.save_model()
        metrics_path = "backend/models/yield_model_metrics.json"
        with open(metrics_path, "w") as f:
            json.dump(metrics, f, indent=2)
        print("\nMulti-model yield comparison:")
        print(f"{'Model':<18}{'Train MAE':>12}{'Test MAE':>12}{'Test R2':>10}")
        print("-" * 52)
        for name, model_metrics in metrics.get("model_metrics", {}).items():
            if name == "ensemble":
                label = "ensemble"
            else:
                label = name
            if not isinstance(model_metrics, dict) or "test_mae" not in model_metrics:
                continue
            print(
                f"{label:<18}"
                f"{model_metrics.get('train_mae', 0):>11.2f}%"
                f"{model_metrics.get('test_mae', 0):>11.2f}%"
                f"{model_metrics.get('test_r2', 0):>10.3f}"
            )
        if metrics.get("skipped_models"):
            print(f"\nSkipped models: {metrics['skipped_models']}")
        print(f"\nBest model: {metrics.get('best_model')}")
        print(f"Saved metrics to {metrics_path}")
        logger.info("Model saved successfully.")
    else:
        logger.error("Training failed.")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
