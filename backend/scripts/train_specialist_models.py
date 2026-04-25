"""
Phase 7 Track B — Train specialist yield models and print per-family metrics.

Usage
-----
  PYTHONPATH=backend python backend/scripts/train_specialist_models.py
"""

import sys, os, json, time
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import logging
logging.basicConfig(
    level=logging.WARNING,
    format="%(levelname)s:%(name)s: %(message)s"
)

from services.specialist_yield_predictor import SpecialistYieldPredictor, REACTION_FAMILIES

# ── Load training data ────────────────────────────────────────────────────────

def load_training_data(paths=("training_reactions.json",
                               "backend/data/training_reactions.json")):
    for p in paths:
        if Path(p).exists():
            with open(p) as f:
                data = json.load(f)
            print(f"  Loaded {len(data)} reactions from {p}")
            return data
    raise FileNotFoundError(
        "training_reactions.json not found. "
        "Run backend/scripts/generate_training_data.py first."
    )


# ── Pretty metrics table ──────────────────────────────────────────────────────

HEADER = (
    f"{'Family':<16}{'Samples':>8}{'Train MAE':>11}{'Test MAE':>10}{'Test R²':>9}"
)
SEP = "-" * len(HEADER)


def print_table(metrics: dict) -> None:
    print()
    print(SEP)
    print(HEADER)
    print(SEP)

    row_order = list(REACTION_FAMILIES.keys()) + ["global_fallback"]
    for family in row_order:
        m = metrics.get(family, {})
        if not m:
            continue
        n   = m.get("n_samples", 0)
        if m.get("skipped"):
            print(f"  {family:<14}{n:>8}{'—':>11}{'—':>10}{'(skipped)':>9}")
            continue
        tm  = m.get("train_mae", 0)
        vm  = m.get("test_mae",  0)
        vr2 = m.get("test_r2",   0)
        print(f"  {family:<14}{n:>8}{tm:>9.2f}%{vm:>9.2f}%{vr2:>9.3f}")

    print(SEP)
    print()


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("Phase 7 Track B — Specialist Yield Model Training")
    print("=" * 60)

    print("\n[1/3] Loading training data ...")
    data = load_training_data()

    print("\n[2/3] Training specialists ...")
    t0 = time.time()
    svp = SpecialistYieldPredictor()
    metrics = svp.train_all(data)
    elapsed = time.time() - t0
    print(f"  Training complete in {elapsed:.1f}s")

    print("\n[3/3] Saving specialist models ...")
    pkl_path = "backend/models/specialist_models.pkl"
    svp.save(pkl_path)
    size_mb = Path(pkl_path).stat().st_size / 1e6
    print(f"  Saved to {pkl_path}  ({size_mb:.1f} MB)")

    print_table(metrics)

    # Quick smoke test
    test_reaction = {
        "reactants": ["Brc1ccccc1", "OB(O)c1ccc(OC)cc1"],
        "products":  ["COc1ccc(-c2ccccc2)cc1"],
        "reaction_type": "suzuki_coupling",
        "temperature_celsius": 80.0,
        "catalyst": "Pd(PPh3)4",
        "solvent": "DMF",
    }
    result = svp.predict_with_uncertainty(test_reaction)
    print("Smoke test (Suzuki coupling):")
    print(f"  yield       = {result['yield_percent']}%")
    print(f"  interval    = [{result['lower_bound']}, {result['upper_bound']}]")
    print(f"  confidence  = {result['confidence_level']}")
    print(f"  model       = {result['model']}")
    print(f"  family      = {result['family']}")
    print(f"  n_train     = {result['n_training_samples']}")


if __name__ == "__main__":
    main()
