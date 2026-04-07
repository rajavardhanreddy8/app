"""
Feedback Endpoint Tests
Test POST /api/feedback, GET /api/feedback/stats, and GET /api/metrics/validation.
"""
import pytest


class TestFeedbackSubmission:

    def test_submit_basic_feedback(self, test_client):
        res = test_client.post(
            "/api/feedback",
            json={
                "target_smiles": "CC(=O)Oc1ccccc1C(=O)O",
                "success": True,
                "notes": "Reaction ran smoothly at 60°C",
            },
        )
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "success"
        assert "feedback_id" in data
        assert len(data["feedback_id"]) > 0

    def test_submit_feedback_with_yield(self, test_client):
        res = test_client.post(
            "/api/feedback",
            json={
                "target_smiles": "CCO",
                "predicted_yield": 75.0,
                "actual_yield": 68.0,
                "success": True,
            },
        )
        assert res.status_code == 200
        assert res.json()["status"] == "success"

    def test_submit_feedback_with_conditions(self, test_client):
        res = test_client.post(
            "/api/feedback",
            json={
                "target_smiles": "c1ccccc1",
                "predicted_yield": 80.0,
                "actual_yield": 72.5,
                "predicted_temperature": 80.0,
                "actual_temperature": 85.0,
                "predicted_conditions": {"catalyst": "Pd", "solvent": "THF"},
                "actual_conditions": {"catalyst": "Pd/C", "solvent": "EtOH"},
                "success": True,
                "notes": "Used different solvent",
            },
        )
        assert res.status_code == 200
        assert res.json()["status"] == "success"

    def test_submit_failed_feedback(self, test_client):
        res = test_client.post(
            "/api/feedback",
            json={
                "target_smiles": "CN1C=NC2=C1C(=O)N(C(=O)N2C)C",
                "predicted_yield": 60.0,
                "actual_yield": 15.0,
                "success": False,
                "notes": "Reaction failed due to moisture contamination",
            },
        )
        assert res.status_code == 200
        assert res.json()["status"] == "success"

    def test_submit_feedback_missing_smiles(self, test_client):
        """Missing required field should return 422."""
        res = test_client.post(
            "/api/feedback",
            json={"success": True},
        )
        assert res.status_code == 422

    def test_submit_feedback_missing_success(self, test_client):
        """Missing required 'success' field should return 422."""
        res = test_client.post(
            "/api/feedback",
            json={"target_smiles": "CCO"},
        )
        assert res.status_code == 422


class TestFeedbackStats:

    def test_stats_endpoint_returns_200(self, test_client):
        res = test_client.get("/api/feedback/stats")
        assert res.status_code == 200

    def test_stats_has_required_keys(self, test_client):
        data = test_client.get("/api/feedback/stats").json()
        assert data["status"] == "success"
        for key in (
            "total_feedback",
            "successful_reactions",
            "success_rate_percent",
            "yield_prediction_mae",
            "yield_samples",
            "temperature_samples",
        ):
            assert key in data

    def test_stats_after_submission(self, test_client):
        """Submit feedback then verify totals include it."""
        # First get baseline
        before = test_client.get("/api/feedback/stats").json()
        before_total = before["total_feedback"]

        # Submit one piece of feedback
        test_client.post(
            "/api/feedback",
            json={
                "target_smiles": "CC(C)Cc1ccc(cc1)C(C)C(=O)O",
                "predicted_yield": 70.0,
                "actual_yield": 65.0,
                "success": True,
            },
        )

        # After count must be at least before + 1
        after = test_client.get("/api/feedback/stats").json()
        assert after["total_feedback"] >= before_total + 1

    def test_yield_mae_is_float_when_data_exists(self, test_client):
        """After submitting yield data, MAE should be a float."""
        # Submit feedback with yield data
        test_client.post(
            "/api/feedback",
            json={
                "target_smiles": "CC(=O)O",
                "predicted_yield": 80.0,
                "actual_yield": 74.0,
                "success": True,
            },
        )
        stats = test_client.get("/api/feedback/stats").json()
        if stats["yield_samples"] > 0:
            assert isinstance(stats["yield_prediction_mae"], float)
            assert stats["yield_prediction_mae"] >= 0


class TestValidationMetrics:

    def test_metrics_endpoint_returns_200(self, test_client):
        res = test_client.get("/api/metrics/validation")
        assert res.status_code == 200

    def test_metrics_has_status_success(self, test_client):
        data = test_client.get("/api/metrics/validation").json()
        assert data["status"] == "success"

    def test_metrics_has_required_keys(self, test_client):
        metrics = test_client.get("/api/metrics/validation").json()["metrics"]
        required_keys = (
            "yield_prediction_mae",
            "temperature_prediction_mae_celsius",
            "route_success_rate_percent",
            "total_feedback_entries",
            "total_synthesis_plans",
            "api_latency",
        )
        for key in required_keys:
            assert key in metrics, f"Missing key: {key}"

    def test_total_synthesis_plans_is_int(self, test_client):
        metrics = test_client.get("/api/metrics/validation").json()["metrics"]
        assert isinstance(metrics["total_synthesis_plans"], int)
        assert metrics["total_synthesis_plans"] >= 0
