import asyncio
import pytest

from services.closed_loop_learning_engine import ClosedLoopLearningEngine
from services.yield_optimization_engine import YieldOptimizationEngine


class FakeCursor:
    def __init__(self, rows):
        self.rows = rows

    async def to_list(self, _limit):
        return list(self.rows)


class FakeCollection:
    def __init__(self):
        self.rows = []

    async def insert_one(self, doc):
        self.rows.append(dict(doc))
        return {"inserted_id": len(self.rows)}

    async def find_one(self, query, projection=None, sort=None):
        matches = [r for r in self.rows if all(r.get(k) == v for k, v in query.items())]
        if not matches:
            return None
        if sort:
            key, direction = sort[0]
            matches.sort(key=lambda r: r.get(key, ""), reverse=(direction == -1))
        row = dict(matches[0])
        if projection:
            row = {k: v for k, v in row.items() if projection.get(k, 1) != 0}
        return row

    async def count_documents(self, query):
        return len([r for r in self.rows if all(r.get(k) == v for k, v in query.items())])

    async def update_one(self, query, update):
        row = await self.find_one(query)
        if not row:
            return
        idx = self.rows.index(next(r for r in self.rows if all(r.get(k) == v for k, v in query.items())))
        if "$set" in update:
            self.rows[idx].update(update["$set"])
        if "$inc" in update:
            for k, v in update["$inc"].items():
                self.rows[idx][k] = self.rows[idx].get(k, 0) + v

    def find(self, query, projection=None):
        rows = [r for r in self.rows if all(r.get(k) == v for k, v in query.items())]
        if projection:
            rows = [{k: v for k, v in r.items() if projection.get(k, 1) != 0} for r in rows]
        return FakeCursor(rows)


class FakeDB:
    def __init__(self):
        self.feedback = FakeCollection()
        self.model_versions = FakeCollection()
        self.learning_events = FakeCollection()
        self.mutation_intelligence = FakeCollection()
        self.synthesis_plans = FakeCollection()


def test_feedback_ingestion_triggers_retraining_at_threshold():
    db = FakeDB()
    engine = ClosedLoopLearningEngine(db=db, retrain_threshold=1)

    result = asyncio.run(engine.ingest_feedback(
        {
            "predicted_route_id": None,
            "actual_yield_percent": 88.0,
            "source": "industrial",
            "mutation_history": ["catalyst_upgrade"],
        }
    ))

    assert result.retrain_triggered is True
    assert result.model_versions["yield_predictor"].startswith("v")
    assert asyncio.run(db.feedback.count_documents({})) == 1


def test_mutation_priorities_flow_into_yield_engine():
    db = FakeDB()
    engine = ClosedLoopLearningEngine(db=db, retrain_threshold=10)

    # two strong positive outcomes for catalyst mutations
    asyncio.run(engine.ingest_feedback({"actual_yield_percent": 95.0, "predicted_route_id": None, "mutation_history": ["catalyst_upgrade"]}))
    asyncio.run(engine.ingest_feedback({"actual_yield_percent": 94.0, "predicted_route_id": None, "mutation_history": ["catalyst_upgrade"]}))

    priorities = asyncio.run(engine.mutation_priorities())
    yield_engine = YieldOptimizationEngine(constraints_engine=None)
    yield_engine.set_mutation_priorities(priorities)

    assert yield_engine.mutation_priority["catalyst_upgrade"] >= 1.0


def test_feedback_validation_rejects_invalid_yield():
    db = FakeDB()
    engine = ClosedLoopLearningEngine(db=db, retrain_threshold=10)

    with pytest.raises(ValueError):
        asyncio.run(engine.ingest_feedback({"actual_yield_percent": 120.0}))
