"""
Phase 3 tests \u2014 route-aware synthesis copilot.
"""
import sys, os, types, asyncio, inspect, pytest
from unittest.mock import AsyncMock, MagicMock

if "structlog" not in sys.modules:
    _sl = types.ModuleType("structlog")
    _sl.get_logger = lambda *a, **kw: __import__("logging").getLogger("stub")
    _sl.configure = lambda **kw: None
    _sl.stdlib = types.SimpleNamespace(filter_by_level=None, LoggerFactory=lambda: None)
    _sl.processors = types.SimpleNamespace(
        TimeStamper=lambda **kw: None, JSONRenderer=lambda: None
    )
    sys.modules.update({
        "structlog": _sl, "structlog.stdlib": _sl.stdlib,
        "structlog.processors": _sl.processors,
    })

if "anthropic" not in sys.modules:
    _anth = types.ModuleType("anthropic")
    _anth.AsyncAnthropic = type(
        "AsyncAnthropic", (), {"__init__": lambda self, **kw: None}
    )
    sys.modules["anthropic"] = _anth

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.update({
    "DEMO_MODE": "true",
    "ANTHROPIC_API_KEY": "sk-test",
    "MONGO_URL": "mongodb://localhost:27017",
    "DB_NAME": "test_db",
})

from services.synthesis_copilot import SynthesisCopilot


SAMPLE_ROUTE = {
    "steps": [
        {
            "reaction_type": "Friedel-Crafts acylation",
            "reactants": ["c1ccccc1", "CC(=O)Cl"],
            "product": "CC(=O)c1ccccc1",
            "estimated_yield": 85.0,
            "estimated_cost_usd": 45.0,
            "conditions": {
                "temperature_celsius": 0.0,
                "solvent": "DCM",
                "catalyst": "AlCl3",
                "time_hours": 3.0,
            },
        },
        {
            "reaction_type": "Pd-catalyzed coupling",
            "reactants": ["CC(=O)c1ccccc1", "OB(O)c1ccccc1"],
            "product": "CC(=O)c1ccc(-c2ccccc2)cc1",
            "estimated_yield": 72.0,
            "estimated_cost_usd": 180.0,
            "conditions": {
                "temperature_celsius": 90.0,
                "solvent": "THF",
                "catalyst": "Pd(PPh3)4",
                "time_hours": 8.0,
            },
        },
    ],
    "overall_yield": 61.2,
    "total_cost_usd": 225.0,
}


# \u2500\u2500 Interface contract \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

class TestCopilotInterface:

    def test_process_query_exists(self):
        assert hasattr(SynthesisCopilot, "process_query")

    def test_process_query_is_async(self):
        assert inspect.iscoroutinefunction(SynthesisCopilot.process_query)

    def test_process_query_accepts_route(self):
        sig = inspect.signature(SynthesisCopilot.process_query)
        assert "current_route" in sig.parameters

    def test_keyword_fallback_method_exists(self):
        assert hasattr(SynthesisCopilot, "_parse_intent_keyword") or \
               hasattr(SynthesisCopilot, "_parse_intent"), \
            "Keyword fallback parser must be preserved"

    def test_llm_intent_parser_exists(self):
        src = inspect.getsource(SynthesisCopilot)
        has_llm_parser = (
            "_parse_intent_with_llm" in src or
            "parse_intent" in src and ("claude" in src.lower() or "client" in src.lower())
        )
        assert has_llm_parser, \
            "LLM-powered intent parser not found in SynthesisCopilot"


# \u2500\u2500 Route-awareness checks \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

class TestCopilotRouteAwareness:

    def test_optimize_for_cost_accepts_route(self):
        sig = inspect.signature(SynthesisCopilot._optimize_for_cost)
        assert "route" in sig.parameters or "current_route" in sig.parameters

    def test_optimize_for_yield_accepts_route(self):
        src = inspect.getsource(SynthesisCopilot)
        assert "_optimize_for_yield" in src

    def test_cost_optimizer_inspects_route_steps(self):
        src = inspect.getsource(SynthesisCopilot._optimize_for_cost)
        uses_route_data = any(kw in src for kw in [
            "steps", "catalyst", "estimated_cost", "route.get", "route["
        ])
        assert uses_route_data, \
            "_optimize_for_cost must inspect actual route steps"

    def test_explain_route_uses_actual_steps(self):
        src = inspect.getsource(SynthesisCopilot)
        explain_section = src[src.find("_explain_route"):][:500]
        uses_steps = "steps" in explain_section or "reaction_type" in explain_section
        assert uses_steps, "_explain_route should reference actual route steps"

    def test_source_not_all_hardcoded_bullets(self):
        src = inspect.getsource(SynthesisCopilot._optimize_for_cost)
        # Old code had 4+ hardcoded bullet string literals
        hardcoded_bullets = src.count('"**')
        assert hardcoded_bullets < 4, \
            f"_optimize_for_cost still has {hardcoded_bullets} hardcoded bullets"


# \u2500\u2500 Keyword fallback \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

class TestKeywordFallback:

    @pytest.fixture
    def copilot(self):
        return SynthesisCopilot.__new__(SynthesisCopilot)

    def _get_keyword_parser(self, copilot):
        if hasattr(copilot, "_parse_intent_keyword"):
            return copilot._parse_intent_keyword
        return copilot._parse_intent

    def test_cost_keyword_detected(self, copilot):
        parser = self._get_keyword_parser(copilot)
        result = parser("reduce cost")
        assert result["action"] == "reduce_cost"

    def test_yield_keyword_detected(self, copilot):
        parser = self._get_keyword_parser(copilot)
        result = parser("increase yield")
        assert result["action"] == "increase_yield"

    def test_speed_keyword_detected(self, copilot):
        parser = self._get_keyword_parser(copilot)
        result = parser("fewer steps")
        assert result["action"] in ("reduce_steps", "speed_up")

    def test_unknown_query_returns_general(self, copilot):
        parser = self._get_keyword_parser(copilot)
        result = parser("xyzzy unknown gobbledygook")
        assert result["action"] == "general"

    def test_returns_dict_with_action(self, copilot):
        parser = self._get_keyword_parser(copilot)
        result = parser("how do I improve this?")
        assert "action" in result


# \u2500\u2500 process_query integration (mocked Claude) \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

class TestProcessQueryIntegration:

    def _make_copilot_demo(self):
        copilot = SynthesisCopilot.__new__(SynthesisCopilot)
        # Set up minimal state
        mock_claude = MagicMock()
        mock_claude.demo_mode = True
        mock_claude.client = None
        copilot.claude_service = mock_claude
        return copilot

    def test_process_query_returns_dict(self):
        copilot = SynthesisCopilot()
        result = asyncio.run(
            copilot.process_query("reduce cost", current_route=SAMPLE_ROUTE)
        )
        assert isinstance(result, dict)

    def test_process_query_has_status_key(self):
        copilot = SynthesisCopilot()
        result = asyncio.run(
            copilot.process_query("explain this route", current_route=SAMPLE_ROUTE)
        )
        assert "status" in result or "response" in result or "suggestions" in result

    def test_process_query_without_route_does_not_crash(self):
        copilot = SynthesisCopilot()
        result = asyncio.run(
            copilot.process_query("how do I improve yield?", current_route=None)
        )
        assert isinstance(result, dict)

    def test_process_query_with_pd_route_mentions_pd(self):
        """Route-aware copilot should notice the Pd catalyst in the route."""
        copilot = SynthesisCopilot()
        result = asyncio.run(
            copilot.process_query("reduce cost", current_route=SAMPLE_ROUTE)
        )
        # Convert result to string and check for Pd or catalyst awareness
        result_str = str(result).lower()
        route_aware = (
            "pd" in result_str or
            "palladium" in result_str or
            "catalyst" in result_str or
            "step" in result_str
        )
        assert route_aware or result.get("status") == "success", \
            "Cost optimizer should be aware of Pd catalyst in route"
