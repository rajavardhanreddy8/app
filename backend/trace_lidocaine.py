import sys
import time
sys.path.append('c:/Users/admin/Desktop/agentic lab/API/rxn1/app/backend')
from services.retrosynthesis_engine import RetrosynthesisEngine
engine = RetrosynthesisEngine()
start = time.time()
routes = engine.search_routes("CCN(CC)CC(=O)Nc1c(C)cccc1C", max_depth=5, max_routes=3)
print(f"Lidocaine Time: {time.time()-start:.2f}s, Routes: {len(routes)}")

routes = engine.search_routes("CC(C)Cc1ccc(cc1)C(C)C(=O)O", max_depth=5, max_routes=3)
print(f"Ibuprofen Routes: {len(routes)}")
