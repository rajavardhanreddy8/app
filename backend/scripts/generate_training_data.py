"""
Script to generate synthetic training data for Phase 2 & 3.
"""
import sys
import os
from pathlib import Path

# Add backend to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.data_downloader import download_ord_subset

def main():
    print("Generating synthetic training data...")
    
    # Ensure backend/data exists
    data_dir = Path("backend/data")
    data_dir.mkdir(parents=True, exist_ok=True)
    
    output_path = data_dir / "training_reactions.json"
    
    # Generate 1000 samples for better model performance and test compliance
    download_ord_subset(str(output_path), n_synthetic=1000)
    
    # Also save a copy for services that expect it in the current dir
    import shutil
    shutil.copy(output_path, "training_reactions.json")
    
    print(f"Done! Data saved to {output_path} (1000 samples)")

if __name__ == "__main__":
    main()
