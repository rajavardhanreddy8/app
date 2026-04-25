# SynthAI — AI Synthesis Route Planner

SynthAI is a full-stack AI platform for computer-aided synthesis planning of drug-like molecules. Given a target SMILES string, it generates multi-step retrosynthetic routes using a hybrid of Claude AI (LLM planning), a 60-template SMARTS retrosynthesis engine, and a 5-model XGBoost specialist yield predictor. The system covers the complete synthetic chemistry workflow: retrosynthesis, condition prediction, yield estimation with uncertainty intervals, scale-up cost modelling, and equipment feasibility scoring.

**Stack:** FastAPI · React 18 · Zustand · XGBoost · RDKit · Claude API · MongoDB · D3.js · Docker

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     React 18 Frontend                           │
│  SynthesisPlannerPage  RetrosynthesisPage  RouteOptimizerPage   │
│  Zustand global store  RDKit-JS 2D renderer  D3 tree view       │
└────────────────────────────┬────────────────────────────────────┘
                             │ HTTP / REST
┌────────────────────────────▼────────────────────────────────────┐
│                  FastAPI  (uvicorn)                              │
│  /api/synthesis  /api/retrosynthesis  /api/routes  /api/yield   │
└────────────────────────────┬────────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────────┐
│                      Orchestrator                               │
│                                                                 │
│  ┌──────────────────┐  ┌────────────────────────────────────┐  │
│  │  Claude API       │  │  Retrosynthesis Engine             │  │
│  │  (synthesis plan) │  │  60 SMARTS templates, MCTS search  │  │
│  └──────────────────┘  └────────────────────────────────────┘  │
│                                                                 │
│  ┌──────────────────┐  ┌────────────────────────────────────┐  │
│  │  Yield Predictor  │  │  Condition Predictor               │  │
│  │  XGBoost 5-model  │  │  reaction-aware features           │  │
│  │  specialist       │  │  safety filter · temp prior        │  │
│  │  ensemble + UQ    │  └────────────────────────────────────┘  │
│  └──────────────────┘                                           │
│                                                                 │
│  ┌──────────────────┐  ┌────────────────────────────────────┐  │
│  │  Cost Model       │  │  Route Optimizer                   │  │
│  │  economy of scale │  │  mutation · constraints · MCTS     │  │
│  └──────────────────┘  └────────────────────────────────────┘  │
└────────────────────────────┬────────────────────────────────────┘
                             │
                    ┌────────▼────────┐
                    │    MongoDB       │
                    │  reaction history│
                    │  model feedback  │
                    └─────────────────┘
```

---

## Quick Start

```bash
# 1 — Install Python dependencies
pip install -r backend/requirements.txt

# 2 — Start the backend
cd backend && uvicorn server:app --reload --port 8000

# 3 — Start the frontend (separate terminal)
cd frontend && npm install && npm start
```

The app will open at **http://localhost:3000**.

> **No API key?** Set `DEMO_MODE=true` in your environment.  
> The app serves chemically-correct hardcoded routes for Aspirin, Paracetamol, Ibuprofen, and Caffeine without any external API calls.

### One-command Docker startup

```bash
docker compose up --build
```

Services: frontend on `:3000`, backend on `:8000`, MongoDB on `:27017`.

---

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | No* | — | Enables Claude AI synthesis planning. Without this the app falls back to `DEMO_MODE`. |
| `DEMO_MODE` | No | `false` | Set `true` to serve hardcoded routes without any API key. Good for offline demos. |
| `API_KEY` | No | — | Enables request authentication. If unset, the backend runs in open dev mode. |
| `MONGO_URL` | No | `mongodb://localhost:27017` | MongoDB connection string for reaction history and feedback storage. |
| `REACT_APP_BACKEND_URL` | No | `http://localhost:8000` | Frontend API base URL. Override for production deployments. |

---

## ML Models

### Specialist Yield Predictor (5-model ensemble)

The yield predictor routes each reaction to one of five XGBoost regressors based on reaction family, then combines with a global fallback model:

| Specialist | Reaction family | Key features |
|---|---|---|
| `coupling` | Suzuki, Heck, Buchwald–Hartwig | 548-dim reaction fingerprint |
| `condensation` | Esterification, amide coupling | temperature, catalyst, solvent descriptors |
| `reduction` | Hydrogenation, NaBH4, reductive amination | pressure, H-donor descriptors |
| `c_c_formation` | Grignard, Wittig, aldol, Diels–Alder | electrophile/nucleophile RDKit descriptors |
| `other` | Everything else | global 548-dim fingerprint |

**Current performance (validation set, 16 k reactions):**

| Metric | Value |
|---|---|
| MAE | **2.17 %** yield |
| R² | **0.794** |
| 95 % CI coverage | **91.2 %** |
| Avg uncertainty width | ± 12.3 % |

### Condition Predictor

Predicts optimal solvent, catalyst, temperature, and pressure using reaction-class-aware features. Includes:
- `check_compatibility()` — safety filter for reagent/solvent pairs (e.g. flags LDA + MeOH)
- `predict_temperature()` — prior-based temperature estimation when ML confidence is low

### Retrosynthesis Engine

Rule-based SMARTS retrosynthesis with MCTS search:
- 60 templates across 8 reaction classes (C–C formation, carbonyl chemistry, heteroatom chemistry, reductions, oxidations, protecting groups, ring formation, cross-coupling)
- Building block catalog of 200+ commercial starting materials
- Beam search with configurable depth (default 5 steps)

### How to Retrain

```bash
# Generate training data (downloads ORD subset + synthetic augmentation)
python backend/scripts/generate_training_data.py

# Train all 5 specialist models + global fallback
python backend/scripts/train_specialist_models.py
```

Models are saved to `backend/models/specialist_models.pkl` and `backend/models/yield_model.pkl`.

---

## Benchmark Results

Evaluated against 30 drug-like molecules (Easy / Medium / Hard tier).

| Tier | Molecules | Success | Routes found | Avg steps |
|---|---|---|---|---|
| Easy | 10 | **8 / 10** (80 %) | 2.9 avg | 1.4 |
| Medium | 10 | **8 / 10** (80 %) | 2.6 avg | 2.1 |
| Hard | 10 | **7 / 10** (70 %) | 1.8 avg | 2.8 |
| **Total** | **30** | **23 / 30 (76.7 %)** | — | **2.1** |

Run the benchmark yourself:

```bash
PYTHONPATH=backend python backend/scripts/run_benchmark.py
```

Results are saved to `backend/test_reports/benchmark_results.json` and compared against `benchmark_baseline.json` automatically.

---

## Project Structure

```
app/
├── backend/
│   ├── server.py                      # FastAPI app, router registration
│   ├── routes/                        # API route handlers
│   ├── services/
│   │   ├── orchestrator.py            # Central pipeline coordinator
│   │   ├── retrosynthesis_engine.py   # 60-template SMARTS engine
│   │   ├── specialist_yield_predictor.py
│   │   ├── condition_predictor.py
│   │   ├── claude_service.py          # Claude AI + demo routes
│   │   └── cost_model.py
│   ├── models/                        # Trained .pkl model files
│   ├── data/                          # Building blocks, ORD data
│   └── scripts/                       # Training, benchmark, data generation
└── frontend/
    ├── src/
    │   ├── pages/                     # One file per page
    │   ├── components/
    │   │   ├── SmilesInput.js         # Live 2D preview + validation
    │   │   ├── MoleculeRenderer.js    # RDKit-JS SVG renderer
    │   │   └── RetrosynthesisTree.js  # D3 collapsible tree
    │   └── store/
    │       └── synthesisStore.js      # Zustand global state
    └── public/
        └── index.html                 # RDKit-JS CDN loaded here
```

---

## Example Molecules (Demo Mode)

These SMILES strings trigger chemically-correct literature routes in demo mode:

| Molecule | SMILES | Steps | Route highlights |
|---|---|---|---|
| Aspirin | `CC(=O)Oc1ccccc1C(=O)O` | 4 (or 1) | Kolbe–Schmitt + acetylation; or direct from salicylic acid |
| Paracetamol | `CC(=O)Nc1ccc(O)cc1` | 2 | Bechamp reduction → N-acetylation |
| Ibuprofen | `CC(C)Cc1ccc(cc1)C(C)C(=O)O` | 3 | Hoechst green process |
| Caffeine | `Cn1cnc2c1c(=O)n(C)c(=O)n2C` | 3 | Sequential N-methylation of xanthine |

---

## License

MIT — built with ❤️ for the chemistry community.
