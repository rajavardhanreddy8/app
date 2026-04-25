import sys
sys.path.append('c:/Users/admin/Desktop/agentic lab/API/rxn1/app/backend')
from services.retrosynthesis_engine import RetrosynthesisEngine
engine = RetrosynthesisEngine()
routes = engine.search_routes("CC(=O)Nc1ccc(O)cc1", max_depth=5, max_routes=3)
print("Routes found:", len(routes))
for r in routes:
    print(r)
