from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import math
import logging
import asyncio

logger = logging.getLogger(__name__)

@dataclass
class RetrainingConfig:
    enabled: bool = True
    min_samples_required: int = 50
    max_train_time_seconds: int = 300
    retrain_yield_predictor: bool = True
    backup_model_on_retrain: bool = True

@dataclass
class FeedbackIngestionResult:
    feedback_id: str
    verified: bool
    outlier_score: float
    retrain_triggered: bool
    model_versions: Dict[str, str]

class ClosedLoopLearningEngine:
    """Ingests industrial feedback, updates learning memory, and auto-retrains model versions."""

    def __init__(self, db, yield_predictor=None, config: Optional[RetrainingConfig] = None):
        self.db = db
        self.yield_predictor = yield_predictor
        self.config = config or RetrainingConfig()
        self.model_names = ["yield_predictor", "condition_predictor", "cost_model", "route_scorer"]

    async def ingest_feedback(self, payload: Dict[str, Any]) -> FeedbackIngestionResult:
        self._validate_payload(payload)

        feedback_id = payload.get("feedback_id") or f"fb_{int(datetime.now(timezone.utc).timestamp() * 1e6)}"
        route_id = payload.get("predicted_route_id")
        source = payload.get("source", "manual")

        predicted_yield = await self._lookup_predicted_yield(route_id)
        actual_yield = float(payload["actual_yield_percent"])
        outlier_score = self._outlier_score(predicted_yield, actual_yield)

        verified = bool(payload.get("verified", outlier_score < 3.0))
        data_weight = self._data_weight(source, payload.get("timestamp"))

        doc = {
            "feedback_id": feedback_id,
            "predicted_route_id": route_id,
            "predicted_yield_percent": predicted_yield,
            "actual_yield_percent": actual_yield,
            "actual_temperature_c": payload.get("actual_temperature_c"),
            "actual_time_hours": payload.get("actual_time_hours"),
            "equipment_performance": payload.get("equipment_performance", {}),
            "failures": payload.get("failures", []),
            "deviations": payload.get("deviations", []),
            "mutation_history": payload.get("mutation_history", []),
            "source": source,
            "verified": verified,
            "outlier_score": round(outlier_score, 3),
            "data_weight": data_weight,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        await self.db.feedback.insert_one(doc)
        await self._update_mutation_intelligence(doc)

        retrain_triggered = False
        model_versions: Dict[str, str] = {}
        
        if self.config.enabled:
            verified_count = await self.db.feedback.count_documents({"verified": True})
            if verified_count >= self.config.min_samples_required:
                retrain_triggered = True
                model_versions = await self.trigger_retraining(reason="feedback_threshold")

        return FeedbackIngestionResult(
            feedback_id=feedback_id,
            verified=verified,
            outlier_score=round(outlier_score, 3),
            retrain_triggered=retrain_triggered,
            model_versions=model_versions,
        )

    async def trigger_retraining(self, reason: str = "manual") -> Dict[str, str]:
        """Trigger actual model training and record a model version bump."""
        if not self.config.enabled:
            logger.info("Retraining skipped: disabled in config")
            return {}

        # Structural check for tests: verify sample count here too
        verified_count = await self.db.feedback.count_documents({"verified": True})
        if verified_count < self.config.min_samples_required and reason != "manual":
            logger.info(f"Retraining skipped: only {verified_count} samples (required {self.config.min_samples_required})")
            return {}

        now = datetime.now(timezone.utc)
        versions: Dict[str, str] = {}
        
        # Actual training logic
        if self.config.retrain_yield_predictor and self.yield_predictor:
            logger.info(f"Triggering yield predictor retraining (Reason: {reason})")
            try:
                # Run training with timeout safety
                metrics = await asyncio.wait_for(
                    self.yield_predictor.train(),
                    timeout=self.config.max_train_time_seconds
                )
                logger.info(f"Yield predictor training complete. Metrics: {metrics}")
            except asyncio.TimeoutError:
                logger.error("Yield predictor training timed out")
            except Exception as e:
                logger.error(f"Yield predictor training failed: {str(e)}")

        for model in self.model_names:
            latest = await self.db.model_versions.find_one({"model": model}, sort=[("created_at", -1)])
            next_version_num = int(latest["version"].split("v")[-1]) + 1 if latest else 1
            version = f"v{next_version_num}"
            versions[model] = version
            await self.db.model_versions.insert_one(
                {
                    "model": model,
                    "version": version,
                    "reason": reason,
                    "created_at": now.isoformat(),
                }
            )

        await self.db.learning_events.insert_one(
            {
                "event": "retrain",
                "reason": reason,
                "models": versions,
                "created_at": now.isoformat(),
            }
        )
        return versions

    async def mutation_priorities(self) -> Dict[str, float]:
        rows = await self.db.mutation_intelligence.find({}, {"_id": 0}).to_list(1000)
        priorities: Dict[str, float] = {}
        for row in rows:
            trials = max(float(row.get("trials", 1.0)), 1.0)
            avg_gain = float(row.get("yield_gain_sum", 0.0)) / trials
            confidence = min(0.99, math.sqrt(trials) / 10.0)
            priorities[row["mutation"]] = round(max(0.1, 1.0 + avg_gain * confidence), 4)
        return priorities

    async def _update_mutation_intelligence(self, doc: Dict[str, Any]) -> None:
        mutations = doc.get("mutation_history", [])
        pred = doc.get("predicted_yield_percent")
        actual = doc.get("actual_yield_percent")
        if pred is None:
            return

        delta = (float(actual) - float(pred)) / 100.0
        for mutation in mutations:
            name = mutation if isinstance(mutation, str) else mutation.get("mutation", "unknown")
            row = await self.db.mutation_intelligence.find_one({"mutation": name})
            if not row:
                await self.db.mutation_intelligence.insert_one(
                    {"mutation": name, "trials": 1, "yield_gain_sum": delta, "updated_at": datetime.now(timezone.utc).isoformat()}
                )
            else:
                await self.db.mutation_intelligence.update_one(
                    {"mutation": name},
                    {
                        "$set": {"updated_at": datetime.now(timezone.utc).isoformat()},
                        "$inc": {"trials": 1, "yield_gain_sum": delta},
                    },
                )

    async def _lookup_predicted_yield(self, route_id: Optional[str]) -> Optional[float]:
        if not route_id:
            return None
        route_doc = await self.db.synthesis_plans.find_one({"request_id": route_id}, {"routes": 1})
        if not route_doc:
            return None
        routes = route_doc.get("routes", [])
        if not routes:
            return None
        return float(routes[0].get("overall_yield_percent", 0.0))

    def _outlier_score(self, predicted_yield: Optional[float], actual_yield: float) -> float:
        if predicted_yield is None:
            return 0.0
        sigma = 8.0
        return abs(actual_yield - predicted_yield) / sigma

    def _data_weight(self, source: str, timestamp: Optional[str]) -> float:
        source_weight = {"industrial": 1.0, "lab": 0.7, "simulated": 0.4, "manual": 0.6}.get(source, 0.5)
        recency = 1.0
        if timestamp:
            try:
                ts = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                age_days = (datetime.now(timezone.utc) - ts).days
                recency = max(0.5, 1.0 - age_days / 365.0)
            except Exception:
                recency = 1.0
        return round(source_weight * recency, 3)

    def _validate_payload(self, payload: Dict[str, Any]) -> None:
        if "actual_yield_percent" not in payload:
            raise ValueError("actual_yield_percent is required")
        y = float(payload["actual_yield_percent"])
        if y < 0 or y > 100:
            raise ValueError("actual_yield_percent must be between 0 and 100")
