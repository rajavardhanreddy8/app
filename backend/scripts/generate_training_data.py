import logging
from pathlib import Path

from services.data_downloader import download_ord_subset


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

    output_path = Path(__file__).resolve().parents[1] / "data" / "training_reactions.json"
    reactions = download_ord_subset(output_path=output_path, n_synthetic=2000)
    print(f"Generated {len(reactions)} reactions. Run yield_predictor.train() to retrain.")
