# SynthAI Curated Retrosynthesis Benchmark

- Benchmark version: `2026.06`
- Report schema: `1.0`
- Cases: 30
- Passed: 23
- Failed: 7
- Errors: 0
- Baseline updates: opt-in only

| Case | Difficulty | Status | Routes | Steps | Failure reasons |
|---|---|---:|---:|---:|---|
| Aspirin | Easy | passed | 3 | 1 | - |
| Paracetamol | Easy | passed | 3 | 1 | - |
| Ethyl acetate | Easy | passed | 3 | 1 | - |
| Benzaldehyde | Easy | passed | 2 | 1 | - |
| Aniline | Easy | passed | 3 | 1 | - |
| Toluene | Easy | failed | 0 | 0 | no_routes_found |
| Phenol | Easy | failed | 0 | 0 | no_routes_found |
| Acetophenone | Easy | passed | 2 | 1 | - |
| Methyl benzoate | Easy | passed | 3 | 1 | - |
| Benzyl alcohol | Easy | passed | 3 | 1 | - |
| Ibuprofen | Medium | passed | 1 | 2 | - |
| Lidocaine | Medium | passed | 3 | 2 | - |
| Atenolol | Medium | passed | 3 | 3 | - |
| Caffeine | Medium | failed | 0 | 0 | no_routes_found |
| Metformin | Medium | passed | 3 | 1 | - |
| Propranolol | Medium | passed | 3 | 1 | - |
| Diazepam | Medium | passed | 1 | 1 | - |
| Naproxen | Medium | passed | 1 | 3 | - |
| Ketoprofen | Medium | passed | 3 | 2 | - |
| Indomethacin | Medium | failed | 0 | 0 | no_routes_found |
| Morphine precursor | Hard | passed | 3 | 1 | - |
| Vitamin C precursor | Hard | passed | 3 | 1 | - |
| Testosterone precursor | Hard | failed | 0 | 0 | no_routes_found |
| Ephedrine | Hard | passed | 3 | 1 | - |
| Amphetamine precursor | Hard | failed | 0 | 0 | no_routes_found |
| Taxol fragment | Hard | passed | 3 | 4 | - |
| Camptothecin fragment | Hard | passed | 1 | 1 | - |
| Quinine skeleton | Hard | passed | 3 | 3 | - |
| Resveratrol | Hard | passed | 2 | 1 | - |
| Capsaicin | Hard | failed | 0 | 0 | no_routes_found |

## Reproducibility

- Python: `3.13.7`
- RDKit: `2025.09.6`
- Config: `{"beam_width": 5, "max_depth": 5, "max_routes": 3}`
- Network data: not used
- Each exception is captured per case; later cases continue running.
