import sys
import time
import json
from pathlib import Path
from datetime import datetime

# Ensure Unicode output works on Windows terminals
try:
    sys.stdout.reconfigure(encoding='utf-8')
except AttributeError:
    pass

from services.retrosynthesis_engine import RetrosynthesisEngine

MOLECULES = {
    'Easy': {
        'Aspirin':        'CC(=O)Oc1ccccc1C(=O)O',
        'Paracetamol':    'CC(=O)Nc1ccc(O)cc1',
        'Ethyl acetate':  'CCOC(C)=O',
        'Benzaldehyde':   'O=Cc1ccccc1',
        'Aniline':        'Nc1ccccc1',
        'Toluene':        'Cc1ccccc1',
        'Phenol':         'Oc1ccccc1',
        'Acetophenone':   'CC(=O)c1ccccc1',
        'Methyl benzoate':'COC(=O)c1ccccc1',
        'Benzyl alcohol': 'OCc1ccccc1',
    },
    'Medium': {
        'Ibuprofen':    'CC(C)Cc1ccc(cc1)C(C)C(=O)O',
        'Lidocaine':    'CCN(CC)CC(=O)Nc1c(C)cccc1C',
        'Atenolol':     'CC(C)NCC(O)COc1ccc(CC(N)=O)cc1',
        'Caffeine':     'Cn1cnc2c1c(=O)n(C)c(=O)n2C',
        'Metformin':    'CN(C)C(=N)NC(=N)N',
        'Propranolol':  'CC(C)NCC(O)COc1cccc2ccccc12',
        'Diazepam':     'CN1C(=O)CN=C(c2ccccc2)c2cc(Cl)ccc21',
        'Naproxen':     'COc1ccc2cc(C(C)C(=O)O)ccc2c1',
        'Ketoprofen':   'CC(C(=O)O)c1ccc(cc1)C(=O)c1ccccc1',
        'Indomethacin': 'CC1=C(CC(=O)O)c2cc(OC)ccc2N1C(=O)c1ccc(Cl)cc1',
    },
    'Hard': {
        'Morphine precursor':   'OC1CC2N(C)CCC12',
        'Vitamin C precursor':  'OCC(O)C1OC(=O)C(O)=C1O',
        'Testosterone precursor':'CC12CCC3C(C1CCC2=O)CCC4=CC(=O)CCC34C',
        'Ephedrine':            'CNC(C)C(O)c1ccccc1',
        'Amphetamine precursor':'CC(N)Cc1ccccc1',
        'Taxol fragment':       'CC(=O)OC1C(=O)c2ccccc2C(=O)O1',
        'Camptothecin fragment':'OC(=O)c1ccc2[nH]c3ccccc3c2c1',
        'Quinine skeleton':     'COc1ccc2nccc(C(O)C3CC=CCN3C)c2c1',
        'Resveratrol':          'Oc1ccc(cc1)/C=C/c1cc(O)cc(O)c1',
        'Capsaicin':            'COc1cc(CNC(=O)CCCC/C=C/CC(C)C)ccc1O',
    },
}

# ── quality flag targets (what we're aiming for) ──────────────────────────────
QUALITY_TARGETS = {
    'Aspirin':      ('contained_salicylic_acid_or_acetyl_chloride', True),
    'Paracetamol':  ('contained_aniline_or_p_aminophenol',          True),
    'Acetophenone': ('involved_friedel_crafts_or_grignard',          True),
}


def analyze_route_molecules(route):
    mols = set(route.get('starting_materials', []))
    for step in route.get('steps', []):
        mols.add(step.get('product', ''))
        for r in step.get('reactants', []):
            mols.add(r)
    return mols


def evaluate_quality_flags(name, routes):
    flags = {}
    if name == 'Aspirin':
        found = any(
            any('O=C(O)c1ccccc1O' in m or 'Oc1ccccc1C(=O)O' in m or 'CC(=O)Cl' in m
                for m in analyze_route_molecules(r))
            for r in routes
        )
        flags['contained_salicylic_acid_or_acetyl_chloride'] = found

    elif name == 'Paracetamol':
        found = any(
            any('Nc1ccccc1' in m or 'Nc1ccc(O)cc1' in m
                for m in analyze_route_molecules(r))
            for r in routes
        )
        flags['contained_aniline_or_p_aminophenol'] = found

    elif name == 'Acetophenone':
        found = False
        for r in routes:
            all_mols = analyze_route_molecules(r)
            has_bz   = any('c1ccccc1' in m and len(m) <= 10 for m in all_mols)
            has_accl = any('CC(=O)Cl' in m for m in all_mols)
            if has_bz and has_accl:
                found = True
                break
        flags['involved_friedel_crafts_or_grignard'] = found

    return flags


# ── helpers ───────────────────────────────────────────────────────────────────
def _summary_from_data(data):
    """Flatten saved JSON into comparable scalars."""
    s   = data.get('summary', {})
    res = data.get('results', {})

    total_mols    = sum(v['count']   for v in s.values())
    total_success = sum(v['success'] for v in s.values())
    grand_steps   = sum(v['total_steps'] for v in s.values())
    grand_time    = sum(v['total_time']  for v in s.values())
    avg_steps = grand_steps / total_success if total_success else 0.0
    avg_time  = grand_time  / total_mols   if total_mols    else 0.0

    quality = {}
    for diff_mols in res.values():
        for mol_name, mol_data in diff_mols.items():
            for flag, val in mol_data.get('quality_flags', {}).items():
                quality[f"{mol_name} / {flag}"] = val

    return {
        'total_success':  total_success,
        'total_mols':     total_mols,
        'easy_success':   s.get('Easy',   {}).get('success', 0),
        'medium_success': s.get('Medium', {}).get('success', 0),
        'hard_success':   s.get('Hard',   {}).get('success', 0),
        'avg_steps':      avg_steps,
        'avg_time':       avg_time,
        'quality':        quality,
    }


def _fmt_change(current, baseline, unit='', higher_is_better=True):
    delta = current - baseline
    if delta == 0:
        arrow = '='
    elif (delta > 0) == higher_is_better:
        arrow = '^'
    else:
        arrow = 'v'
    sign = '+' if delta >= 0 else ''
    return f"{sign}{delta:{'.1f' if isinstance(delta, float) else 'd'}}{unit}  {arrow}"


# ── main benchmark ────────────────────────────────────────────────────────────
def run_benchmark():
    report_dir  = Path('backend/test_reports')
    report_dir.mkdir(parents=True, exist_ok=True)
    baseline_path = report_dir / 'benchmark_baseline.json'

    # Load existing baseline if present
    old_data = None
    if baseline_path.exists():
        try:
            with open(baseline_path) as f:
                old_data = json.load(f)
        except Exception:
            old_data = None

    engine  = RetrosynthesisEngine()
    results = {}
    summary_stats = {}
    total_mols    = 0
    total_success = 0

    for difficulty, molecules in MOLECULES.items():
        results[difficulty] = {}
        diff_stats = {'count': len(molecules), 'success': 0,
                      'total_steps': 0, 'total_time': 0.0}

        for name, smiles in molecules.items():
            t0     = time.time()
            routes = engine.search_routes(smiles, max_depth=5, max_routes=3)
            elapsed = time.time() - t0

            num_routes = len(routes)
            num_steps  = 0
            best_score = 0.0
            starting_materials = []

            if num_routes > 0:
                best_route = routes[0]
                num_steps  = best_route.get('num_steps', 0)
                best_score = best_route.get('score', 0.0)
                starting_materials = best_route.get('starting_materials', [])

            success = num_routes > 0 and num_steps > 0

            if success:
                diff_stats['success']     += 1
                diff_stats['total_steps'] += num_steps
            diff_stats['total_time'] += elapsed
            total_mols    += 1
            if success:
                total_success += 1

            flags = evaluate_quality_flags(name, routes)

            mol_result = {
                'smiles':                  smiles,
                'num_routes_found':        num_routes,
                'num_steps_in_best_route': num_steps,
                'best_route_score':        best_score,
                'time_taken_seconds':      elapsed,
                'starting_materials_found':starting_materials,
                'success':                 success,
            }
            if flags:
                mol_result['quality_flags'] = flags

            results[difficulty][name] = mol_result
            print(f"[{difficulty}] {name}: {'SUCCESS' if success else 'FAIL'} "
                  f"in {elapsed:.2f}s ({num_steps} steps)")

        summary_stats[difficulty] = diff_stats

    # ── current run stats ─────────────────────────────────────────────────────
    grand_steps   = sum(v['total_steps'] for v in summary_stats.values())
    grand_success = sum(v['success']     for v in summary_stats.values())
    grand_time    = sum(v['total_time']  for v in summary_stats.values())
    avg_steps_cur = grand_steps / grand_success if grand_success else 0.0
    avg_time_cur  = grand_time  / total_mols    if total_mols    else 0.0

    # ── print summary table ───────────────────────────────────────────────────
    print("\n\n" + "=" * 55)
    print(f"BENCHMARK RESULTS - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 55)
    print(f"{'Difficulty':<12} {'Molecules':<10} {'Success':<8} {'Avg Steps':<10} {'Avg Time':<10}")
    print("-" * 55)
    for diff in ['Easy', 'Medium', 'Hard']:
        st    = summary_stats[diff]
        count = st['count']
        succ  = st['success']
        avg_s = st['total_steps'] / succ  if succ  else 0.0
        avg_t = st['total_time']  / count if count else 0.0
        print(f"{diff:<12} {count:<10} {succ}/{count:<5} {avg_s:<10.1f} {avg_t:.2f}s")
    print("-" * 55)
    print(f"{'TOTAL':<12} {total_mols:<10} {grand_success}/{total_mols:<5} "
          f"{avg_steps_cur:<10.1f} {avg_time_cur:.2f}s")
    print("=" * 55)

    # Quality flags
    print("\nQuality Flags:")
    for diff, mols in results.items():
        for mol_name, metrics in mols.items():
            if 'quality_flags' in metrics:
                print(f"  {mol_name}:")
                for k, v in metrics['quality_flags'].items():
                    target_flag = QUALITY_TARGETS.get(mol_name, (None, None))
                    needs = f"  ← target: {target_flag[1]}" if target_flag[0] == k and v != target_flag[1] else ""
                    print(f"    - {k}: {v}{needs}")

    # ── comparison table ──────────────────────────────────────────────────────
    if old_data:
        old = _summary_from_data(old_data)

        print("\n\n" + "=" * 65)
        print("BENCHMARK COMPARISON  (baseline vs current)")
        print("=" * 65)
        print(f"  Baseline timestamp : {old_data.get('timestamp', 'unknown')}")
        print(f"  Current  timestamp : {datetime.now().isoformat()}")
        print("=" * 65)
        print(f"{'Metric':<32} {'Baseline':<12} {'Current':<12} {'Change'}")
        print("-" * 65)

        rows = [
            ("Overall success",
             f"{old['total_success']}/{old['total_mols']}",
             f"{grand_success}/{total_mols}",
             _fmt_change(grand_success, old['total_success'], higher_is_better=True)),
            ("Easy success",
             f"{old['easy_success']}/10",
             f"{summary_stats['Easy']['success']}/10",
             _fmt_change(summary_stats['Easy']['success'], old['easy_success'], higher_is_better=True)),
            ("Medium success",
             f"{old['medium_success']}/10",
             f"{summary_stats['Medium']['success']}/10",
             _fmt_change(summary_stats['Medium']['success'], old['medium_success'], higher_is_better=True)),
            ("Hard success",
             f"{old['hard_success']}/10",
             f"{summary_stats['Hard']['success']}/10",
             _fmt_change(summary_stats['Hard']['success'], old['hard_success'], higher_is_better=True)),
            ("Avg steps (successes)",
             f"{old['avg_steps']:.1f}",
             f"{avg_steps_cur:.1f}",
             _fmt_change(avg_steps_cur, old['avg_steps'], unit='', higher_is_better=True)),
            ("Avg time per molecule",
             f"{old['avg_time']:.2f}s",
             f"{avg_time_cur:.2f}s",
             ""),
        ]
        for label, baseline_val, cur_val, change in rows:
            print(f"  {label:<30} {baseline_val:<12} {cur_val:<12} {change}")

        # Quality flag comparison
        print("-" * 65)
        print(f"  {'Quality flag':<30} {'Baseline':<12} {'Current':<12} {'Target'}")
        print("-" * 65)
        for mol_name, (flag_key, target_val) in QUALITY_TARGETS.items():
            old_key = f"{mol_name} / {flag_key}"
            old_val = old['quality'].get(old_key, '?')
            # get current
            cur_val = results.get(
                next((d for d in MOLECULES if mol_name in MOLECULES[d]), ''), {}
            ).get(mol_name, {}).get('quality_flags', {}).get(flag_key, '?')
            label = f"{mol_name}: {flag_key[:22]}"
            marker = "  ← target!" if cur_val != target_val else ""
            print(f"  {label:<30} {str(old_val):<12} {str(cur_val):<12} {target_val}{marker}")

        print("=" * 65)

        # ── decide whether to overwrite baseline ──────────────────────────
        is_better = grand_success > old['total_success'] or (
            grand_success == old['total_success'] and avg_steps_cur > old['avg_steps']
        )
        if is_better:
            print("\n[OK]  Current results are BETTER than baseline -> overwriting baseline.")
        else:
            print("\n[!!]  Current results are NOT better than baseline -> keeping old baseline.")

    else:
        is_better = True  # No baseline yet -> always save
        print("\n(No previous baseline found — saving as new baseline.)")

    # ── save ──────────────────────────────────────────────────────────────────
    output_data = {
        'timestamp': datetime.now().isoformat(),
        'summary':   summary_stats,
        'results':   results,
    }
    if is_better or not old_data:
        with open(baseline_path, 'w') as f:
            json.dump(output_data, f, indent=2)
        print(f"[SAVED]  Written to {baseline_path}")
    else:
        alt_path = report_dir / f"benchmark_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(alt_path, 'w') as f:
            json.dump(output_data, f, indent=2)
        print(f"[SAVED]  Current run (not baseline) written to {alt_path}")


if __name__ == '__main__':
    run_benchmark()
