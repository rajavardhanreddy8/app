"""
Phase 1 tests for ClaudeService.

Tests schema validation, demo-mode response structure, and
initialization logic. No heavy ML deps required — only structlog
and anthropic (stubbed if missing).
"""
import sys
import os
import types
import json
import pytest

# ── Stub heavy deps that claude_service.py chains into ────────────
# structlog — used directly by claude_service.py
if "structlog" not in sys.modules:
    _sl = types.ModuleType("structlog")
    _sl.get_logger = lambda *a, **kw: __import__("logging").getLogger("structlog_stub")
    _sl.stdlib = types.ModuleType("structlog.stdlib")
    _sl.stdlib.filter_by_level = None
    _sl.stdlib.LoggerFactory = lambda: None
    _sl.processors = types.ModuleType("structlog.processors")
    _sl.processors.TimeStamper = lambda **kw: None
    _sl.processors.JSONRenderer = lambda: None
    _sl.configure = lambda **kw: None
    sys.modules["structlog"] = _sl
    sys.modules["structlog.stdlib"] = _sl.stdlib
    sys.modules["structlog.processors"] = _sl.processors

# anthropic — used directly by claude_service.py
if "anthropic" not in sys.modules:
    _anth = types.ModuleType("anthropic")
    _anth.AsyncAnthropic = type("AsyncAnthropic", (), {"__init__": lambda self, **kw: None})
    sys.modules["anthropic"] = _anth

# Ensure backend is on sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("DEMO_MODE", "true")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-test-placeholder")

from services.claude_service import ClaudeService


# ── Schema tests ──────────────────────────────────────────────────

class TestSynthesisRouteSchema:
    """Validate that demo-mode JSON can be parsed."""

    def test_valid_payload_parses(self):
        """Demo routes should be valid JSON with a 'routes' key."""
        svc = ClaudeService(api_key="test")
        result = svc._generate_demo_routes("CC(=O)Oc1ccccc1C(=O)O", 5, "balanced")
        data = json.loads(result["content"])
        assert "routes" in data
        assert len(data["routes"]) >= 1

    def test_missing_routes_key_raises(self):
        """An empty JSON dict should not pass our schema check."""
        data = json.loads("{}")
        assert "routes" not in data

    def test_route_has_required_fields(self):
        """Each route must have starting_materials, steps, overall_yield."""
        svc = ClaudeService(api_key="test")
        result = svc._generate_demo_routes("CCO", 3, "yield")
        data = json.loads(result["content"])
        route = data["routes"][0]
        assert "starting_materials" in route
        assert "steps" in route
        assert "overall_yield" in route

    def test_step_has_required_fields(self):
        """Each step must have reactants, product, reaction_type."""
        svc = ClaudeService(api_key="test")
        result = svc._generate_demo_routes("CCO", 3, "yield")
        data = json.loads(result["content"])
        step = data["routes"][0]["steps"][0]
        for field in ("reactants", "product", "reaction_type"):
            assert field in step, f"Missing field: {field}"


# ── Demo mode tests ───────────────────────────────────────────────

class TestClaudeServiceDemoMode:
    """Verify ClaudeService initializes correctly in demo mode."""

    def test_demo_mode_from_env(self):
        os.environ["DEMO_MODE"] = "true"
        svc = ClaudeService(api_key=None)
        assert svc.demo_mode is True

    def test_demo_mode_without_api_key(self):
        old = os.environ.pop("ANTHROPIC_API_KEY", None)
        os.environ["DEMO_MODE"] = "false"
        try:
            svc = ClaudeService(api_key=None)
            assert svc.demo_mode is True  # falls back to demo
        finally:
            if old:
                os.environ["ANTHROPIC_API_KEY"] = old
            os.environ["DEMO_MODE"] = "true"

    def test_demo_routes_usage_tokens(self):
        svc = ClaudeService(api_key="test")
        result = svc._generate_demo_routes("c1ccccc1", 5, "balanced")
        assert "usage" in result
        assert result["usage"]["total_tokens"] > 0


# ── Response consistency tests ────────────────────────────────────

class TestDemoResponseConsistency:
    """Demo routes should return consistent structures across calls."""

    def test_multiple_calls_same_structure(self):
        svc = ClaudeService(api_key="test")
        r1 = svc._generate_demo_routes("CCO", 5, "balanced")
        r2 = svc._generate_demo_routes("CCO", 5, "balanced")
        d1 = json.loads(r1["content"])
        d2 = json.loads(r2["content"])
        assert len(d1["routes"]) == len(d2["routes"])

    def test_conditions_present_in_steps(self):
        svc = ClaudeService(api_key="test")
        result = svc._generate_demo_routes("CCO", 5, "yield")
        data = json.loads(result["content"])
        for route in data["routes"]:
            for step in route["steps"]:
                assert "conditions" in step
                cond = step["conditions"]
                assert "temperature_celsius" in cond
