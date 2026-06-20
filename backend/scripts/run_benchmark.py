"""Run the curated, reproducible SynthAI retrosynthesis benchmark.

Every case is recorded. A chemistry failure or runtime exception never removes
the remaining cases from the report, and baseline updates are opt-in.
"""

import argparse
import json
import platform
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass

from rdkit import rdBase

from services.retrosynthesis_engine import RetrosynthesisEngine


BENCHMARK_NAME = "synthai_curated_retrosynthesis"
BENCHMARK_VERSION = "2026.06"
REPORT_SCHEMA_VERSION = "1.0"
DEFAULT_CONFIG = {"max_depth": 5, "max_routes": 3, "beam_width": 5}

MOLECULES = {
    "Easy": {
        "Aspirin": "CC(=O)Oc1ccccc1C(=O)O",
        "Paracetamol": "CC(=O)Nc1ccc(O)cc1",
        "Ethyl acetate": "CCOC(C)=O",
        "Benzaldehyde": "O=Cc1ccccc1",
        "Aniline": "Nc1ccccc1",
        "Toluene": "Cc1ccccc1",
        "Phenol": "Oc1ccccc1",
        "Acetophenone": "CC(=O)c1ccccc1",
        "Methyl benzoate": "COC(=O)c1ccccc1",
        "Benzyl alcohol": "OCc1ccccc1",
    },
    "Medium": {
        "Ibuprofen": "CC(C)Cc1ccc(cc1)C(C)C(=O)O",
        "Lidocaine": "CCN(CC)CC(=O)Nc1c(C)cccc1C",
        "Atenolol": "CC(C)NCC(O)COc1ccc(CC(N)=O)cc1",
        "Caffeine": "Cn1cnc2c1c(=O)n(C)c(=O)n2C",
        "Metformin": "CN(C)C(=N)NC(=N)N",
        "Propranolol": "CC(C)NCC(O)COc1cccc2ccccc12",
        "Diazepam": "CN1C(=O)CN=C(c2ccccc2)c2cc(Cl)ccc21",
        "Naproxen": "COc1ccc2cc(C(C)C(=O)O)ccc2c1",
        "Ketoprofen": "CC(C(=O)O)c1ccc(cc1)C(=O)c1ccccc1",
        "Indomethacin": "CC1=C(CC(=O)O)c2cc(OC)ccc2N1C(=O)c1ccc(Cl)cc1",
    },
    "Hard": {
        "Morphine precursor": "OC1CC2N(C)CCC12",
        "Vitamin C precursor": "OCC(O)C1OC(=O)C(O)=C1O",
        "Testosterone precursor": "CC12CCC3C(C1CCC2=O)CCC4=CC(=O)CCC34C",
        "Ephedrine": "CNC(C)C(O)c1ccccc1",
        "Amphetamine precursor": "CC(N)Cc1ccccc1",
        "Taxol fragment": "CC(=O)OC1C(=O)c2ccccc2C(=O)O1",
        "Camptothecin fragment": "OC(=O)c1ccc2[nH]c3ccccc3c2c1",
        "Quinine skeleton": "COc1ccc2nccc(C(O)C3CC=CCN3C)c2c1",
        "Resveratrol": "Oc1ccc(cc1)/C=C/c1cc(O)cc(O)c1",
        "Capsaicin": "COc1cc(CNC(=O)CCCC/C=C/CC(C)C)ccc1O",
    },
}

QUALITY_TARGETS = {
    "Aspirin": "contained_salicylic_acid_or_acetyl_chloride",
    "Paracetamol": "contained_aniline_or_p_aminophenol",
    "Acetophenone": "involved_friedel_crafts_or_grignard",
}


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def curated_cases() -> Iterable[Tuple[str, str, str, str]]:
    """Yield stable case IDs, difficulty, name, and SMILES."""
    for difficulty, molecules in MOLECULES.items():
        for index, (name, smiles) in enumerate(molecules.items(), start=1):
            case_id = f"{difficulty.lower()}-{index:02d}-{_slug(name)}"
            yield case_id, difficulty, name, smiles


def _route_molecules(route: Dict[str, Any]) -> set:
    molecules = set(route.get("starting_materials", []))
    for step in route.get("steps", []):
        molecules.add(step.get("product", ""))
        molecules.update(step.get("reactants", []))
    return molecules


def evaluate_quality_flags(name: str, routes: List[Dict[str, Any]]) -> Dict[str, bool]:
    flags: Dict[str, bool] = {}
    if name == "Aspirin":
        flags[QUALITY_TARGETS[name]] = any(
            any(
                "O=C(O)c1ccccc1O" in molecule
                or "Oc1ccccc1C(=O)O" in molecule
                or "CC(=O)Cl" in molecule
                for molecule in _route_molecules(route)
            )
            for route in routes
        )
    elif name == "Paracetamol":
        flags[QUALITY_TARGETS[name]] = any(
            any(
                "Nc1ccccc1" in molecule or "Nc1ccc(O)cc1" in molecule
                for molecule in _route_molecules(route)
            )
            for route in routes
        )
    elif name == "Acetophenone":
        flags[QUALITY_TARGETS[name]] = any(
            any("c1ccccc1" in molecule and len(molecule) <= 10 for molecule in _route_molecules(route))
            and any("CC(=O)Cl" in molecule for molecule in _route_molecules(route))
            for route in routes
        )
    return flags


def run_case(
    engine: RetrosynthesisEngine,
    case_id: str,
    difficulty: str,
    name: str,
    smiles: str,
    config: Dict[str, int],
) -> Dict[str, Any]:
    """Run one case and always return a complete, serializable record."""
    started = time.perf_counter()
    record: Dict[str, Any] = {
        "case_id": case_id,
        "difficulty": difficulty,
        "name": name,
        "smiles": smiles,
        "status": "error",
        "success": False,
        "failure_reasons": [],
        "num_routes_found": 0,
        "num_steps_in_best_route": 0,
        "best_route_score": 0.0,
        "starting_materials_found": [],
        "reaction_types": [],
        "quality_flags": {},
        "error": None,
    }
    try:
        routes = engine.search_routes(
            smiles,
            max_depth=config["max_depth"],
            max_routes=config["max_routes"],
            beam_width=config["beam_width"],
        )
        record["num_routes_found"] = len(routes)
        if not routes:
            record["failure_reasons"].append("no_routes_found")
        else:
            best_route = routes[0]
            record["num_steps_in_best_route"] = int(best_route.get("num_steps", 0) or 0)
            record["best_route_score"] = float(best_route.get("score", 0.0) or 0.0)
            record["starting_materials_found"] = best_route.get("starting_materials", [])
            record["reaction_types"] = [
                str(step.get("reaction_type", "unknown")) for step in best_route.get("steps", [])
            ]
            if record["num_steps_in_best_route"] <= 0:
                record["failure_reasons"].append("best_route_has_no_steps")

        quality_flags = evaluate_quality_flags(name, routes)
        record["quality_flags"] = quality_flags
        for flag, passed in quality_flags.items():
            if not passed:
                record["failure_reasons"].append(f"quality_target_failed:{flag}")

        record["success"] = not record["failure_reasons"]
        record["status"] = "passed" if record["success"] else "failed"
    except Exception as exc:
        record["status"] = "error"
        record["failure_reasons"] = [f"exception:{type(exc).__name__}"]
        record["error"] = {"type": type(exc).__name__, "message": str(exc)}
    finally:
        record["time_taken_seconds"] = round(time.perf_counter() - started, 6)
    return record


def summarize(cases: List[Dict[str, Any]]) -> Dict[str, Any]:
    by_difficulty: Dict[str, Dict[str, int]] = {}
    for difficulty in MOLECULES:
        selected = [case for case in cases if case["difficulty"] == difficulty]
        by_difficulty[difficulty] = {
            "total": len(selected),
            "passed": sum(case["status"] == "passed" for case in selected),
            "failed": sum(case["status"] == "failed" for case in selected),
            "errors": sum(case["status"] == "error" for case in selected),
        }
    return {
        "total": len(cases),
        "passed": sum(case["status"] == "passed" for case in cases),
        "failed": sum(case["status"] == "failed" for case in cases),
        "errors": sum(case["status"] == "error" for case in cases),
        "by_difficulty": by_difficulty,
        "failure_cases": [
            {"case_id": case["case_id"], "reasons": case["failure_reasons"]}
            for case in cases
            if case["status"] != "passed"
        ],
    }


def render_markdown(report: Dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# SynthAI Curated Retrosynthesis Benchmark",
        "",
        f"- Benchmark version: `{report['benchmark']['version']}`",
        f"- Report schema: `{report['schema_version']}`",
        f"- Cases: {summary['total']}",
        f"- Passed: {summary['passed']}",
        f"- Failed: {summary['failed']}",
        f"- Errors: {summary['errors']}",
        "- Baseline updates: opt-in only",
        "",
        "| Case | Difficulty | Status | Routes | Steps | Failure reasons |",
        "|---|---|---:|---:|---:|---|",
    ]
    for case in report["cases"]:
        reasons = ", ".join(case["failure_reasons"]) or "-"
        lines.append(
            f"| {case['name']} | {case['difficulty']} | {case['status']} | "
            f"{case['num_routes_found']} | {case['num_steps_in_best_route']} | {reasons} |"
        )
    lines.extend([
        "",
        "## Reproducibility",
        "",
        f"- Python: `{report['environment']['python']}`",
        f"- RDKit: `{report['environment']['rdkit']}`",
        f"- Config: `{json.dumps(report['config'], sort_keys=True)}`",
        "- Network data: not used",
        "- Each exception is captured per case; later cases continue running.",
        "",
    ])
    return "\n".join(lines)


def run_benchmark(
    output_dir: Path,
    config: Dict[str, int],
    update_baseline: bool = False,
) -> Dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    started_at = datetime.now(timezone.utc)
    started = time.perf_counter()
    engine = RetrosynthesisEngine()
    case_results = []

    for case_id, difficulty, name, smiles in curated_cases():
        result = run_case(engine, case_id, difficulty, name, smiles, config)
        case_results.append(result)
        reasons = ", ".join(result["failure_reasons"]) or "none"
        print(f"[{difficulty}] {name}: {result['status'].upper()} ({reasons})")

    report = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "benchmark": {
            "name": BENCHMARK_NAME,
            "version": BENCHMARK_VERSION,
            "curated": True,
            "deterministic": True,
            "network_data_used": False,
        },
        "environment": {
            "python": platform.python_version(),
            "rdkit": rdBase.rdkitVersion,
            "platform": platform.platform(),
        },
        "config": config,
        "started_at": started_at.isoformat(),
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "duration_seconds": round(time.perf_counter() - started, 6),
        "summary": summarize(case_results),
        "cases": case_results,
    }

    json_path = output_dir / "benchmark_report.json"
    markdown_path = output_dir / "benchmark_report.md"
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    if update_baseline:
        (output_dir / "benchmark_baseline_v2.json").write_text(
            json.dumps(report, indent=2), encoding="utf-8"
        )

    print(
        f"Recorded {report['summary']['total']} cases: "
        f"{report['summary']['passed']} passed, "
        f"{report['summary']['failed']} failed, "
        f"{report['summary']['errors']} errors."
    )
    print(f"JSON report: {json_path}")
    print(f"Markdown report: {markdown_path}")
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("backend/test_reports"))
    parser.add_argument("--max-depth", type=int, default=DEFAULT_CONFIG["max_depth"])
    parser.add_argument("--max-routes", type=int, default=DEFAULT_CONFIG["max_routes"])
    parser.add_argument("--beam-width", type=int, default=DEFAULT_CONFIG["beam_width"])
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="Explicitly replace benchmark_baseline_v2.json with this run.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = {
        "max_depth": args.max_depth,
        "max_routes": args.max_routes,
        "beam_width": args.beam_width,
    }
    run_benchmark(args.output_dir, config, update_baseline=args.update_baseline)


if __name__ == "__main__":
    main()
