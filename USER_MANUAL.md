# SynthAI User Manual

## Local Startup

### Backend

Install Python 3.11+ and run:

```bash
cd app/backend
pip install -r requirements.txt
set DEMO_MODE=true
uvicorn server:app --reload --port 8000
```

The API runs at `http://localhost:8000`.

### Frontend

In another terminal:

```bash
cd app/frontend
npm install
npm start
```

The UI runs at `http://localhost:3000`.

The frontend reads `REACT_APP_BACKEND_URL` from `app/frontend/.env`. The default is:

```text
REACT_APP_BACKEND_URL=http://localhost:8000
```

## Demo Mode

Use demo mode when no Anthropic API key is available:

```bash
set DEMO_MODE=true
```

Demo mode supports known molecules such as:

| Molecule | SMILES |
|---|---|
| Aspirin | `CC(=O)Oc1ccccc1C(=O)O` |
| Paracetamol | `CC(=O)Nc1ccc(O)cc1` |
| Ibuprofen | `CC(C)Cc1ccc(cc1)C(C)C(=O)O` |
| Caffeine | `Cn1cnc2c1c(=O)n(C)c(=O)n2C` |

## Generate Results

1. Start backend and frontend.
2. Open `http://localhost:3000`.
3. Go to `AI Synthesis Planner`.
4. Enter a target SMILES.
5. Select max steps and optimization goal.
6. Click `Generate Synthesis Plan`.
7. Review the generated route cards.

Each route card contains:

- Starting materials.
- Reaction steps.
- Estimated yield.
- Estimated cost.
- Estimated time.
- Conditions, if available.
- Overall route score.

## Advanced Mode

Enable `Advanced Mode` on the planner for industrial review.

Set:

- Production scale: lab, pilot, or industrial.
- Batch size in kg.

Advanced mode adds scale-aware optimization, industrial cost modeling, and process feasibility checks.

## API Quick Checks

Health check:

```bash
curl http://localhost:8000/api/health
```

Plan synthesis:

```bash
curl -X POST http://localhost:8000/api/synthesis/plan ^
  -H "Content-Type: application/json" ^
  -d "{\"target_smiles\":\"CC(=O)Oc1ccccc1C(=O)O\",\"max_steps\":5,\"optimize_for\":\"balanced\"}"
```

## Troubleshooting

### Frontend shows network errors

Check that the backend is running on `http://localhost:8000` and that `app/frontend/.env` points to the same URL.

### Backend says `ANTHROPIC_API_KEY not configured`

Set `DEMO_MODE=true` for local demos, or provide `ANTHROPIC_API_KEY`.

### MongoDB is not running

The backend falls back to an in-memory mock database. Planning still works, but history and feedback are not persisted.

### PowerShell blocks `npm`

Use `npm.cmd` instead:

```bash
npm.cmd start
```

### Python command is missing

Install Python 3.11+ and ensure it is on PATH, then reopen the terminal.

