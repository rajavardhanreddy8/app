import asyncio
import logging

from services.yield_predictor import QuantileYieldPredictor


async def _main():
    predictor = QuantileYieldPredictor()
    metrics = await predictor.train()

    if not metrics:
        print("Quantile model training failed or insufficient data.")
        return

    print(
        f"Q10/Q50/Q90 models trained. Q50 MAE: {metrics['q50_mae']:.1f}%, "
        "saved to yield_model_quantile.pkl"
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(_main())
