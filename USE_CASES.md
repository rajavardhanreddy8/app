# SynthAI Application Use Cases

SynthAI supports computer-aided synthesis planning and process review for drug-like molecules represented as SMILES strings.

## 1. Generate a Synthesis Plan

Use this when a chemist has a target molecule and needs candidate synthetic routes.

- Open `AI Synthesis Planner`.
- Enter a valid target SMILES, for example aspirin: `CC(=O)Oc1ccccc1C(=O)O`.
- Select the optimization goal: balanced, high yield, low cost, or fast.
- Click `Generate Synthesis Plan`.

Expected result: one or more routes with starting materials, step-by-step reactions, estimated yield, cost, time, conditions, and route score.

## 2. Validate and Analyze Molecules

Use this before planning routes or when checking user-entered SMILES.

- Open `Molecule Analyzer`.
- Enter a SMILES string.
- Run analysis.

Expected result: validity status plus molecular properties such as molecular weight and other RDKit-derived descriptors.

## 3. Retrosynthesis Search

Use this when you want rule-based disconnections rather than a full AI plan.

- Open `Retrosynthesis`.
- Enter the target SMILES.
- Choose search depth and route count.
- Generate routes.

Expected result: retrosynthetic route candidates from the template engine.

## 4. Predict Reaction Conditions

Use this when a route step needs estimated solvent, catalyst, temperature, or pressure.

- Open `Condition Predictor`.
- Enter reactant and product SMILES.
- Optionally provide reaction type.
- Predict conditions.

Expected result: recommended conditions and compatibility-aware safety output.

## 5. Optimize a Route

Use this after generating a route and selecting the best candidate.

- Generate a synthesis plan first.
- Open `Route Optimizer`.
- Optimize the selected route.

Expected result: route mutations, confidence score, constraint feedback, and equipment feasibility.

## 6. Scale-Up and Industrial Review

Use this when moving a reaction from lab scale toward pilot or production scale.

- Open `Scale-Up`.
- Provide a reaction or select an existing route step.
- Choose lab, pilot, or industrial scale.
- Enter batch size.

Expected result: scale-adjusted parameters, cost estimates, process constraints, and warnings.

## 7. Closed-Loop Learning

Use this after real experimental results are available.

- Submit actual yield, process deviations, failures, and equipment feedback.
- Trigger retraining when enough verified feedback has accumulated.

Expected result: feedback captured for model improvement and mutation priorities updated for future optimization.

