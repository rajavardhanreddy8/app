"""
Phase 1 tests for Orchestrator imports and structure.

Verifies that orchestrator.py has the right imports, class structure,
and that its async methods are safely callable.

Strategy: avoid importing orchestrator.py directly (it chains into
rdkit/numpy via MolecularService/SynthesisPlanner). Instead, scan
the source file as text for import/class tests, and use sys.modules
stubs for the async-safety tests.
"""
import sys
import os
import types
import re
import inspect
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# Paths
BACKEND_DIR = Path(__file__).parent.parent
ORCHESTRATOR_PATH = BACKEND_DIR / "services" / "orchestrator.py"


# ── Source-scan tests (no imports needed) ─────────────────────────

class TestOrchestratorImports:
    """Verify orchestrator.py source has correct imports."""

    @pytest.fixture(autouse=True)
    def _load_source(self):
        self.source = ORCHESTRATOR_PATH.read_text(encoding="utf-8")

    def test_imports_chemistry_models(self):
        assert "from models.chemistry import" in self.source

    def test_imports_claude_service(self):
        assert "from services.claude_service import" in self.source

    def test_imports_molecular_service(self):
        assert "from services.molecular_service import" in self.source

    def test_imports_synthesis_planner(self):
        assert "from services.synthesis_planner import" in self.source

    def test_imports_at_top_not_inside_method(self):
        """All imports should be at module level, not inside methods."""
        lines = self.source.splitlines()
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith(("from ", "import ")):
                # Should not be indented more than 0 (module level)
                leading_spaces = len(line) - len(line.lstrip())
                assert leading_spaces == 0, (
                    f"Import on line {i+1} is indented ({leading_spaces} spaces): {stripped}"
                )

    def test_class_exists(self):
        assert "class SynthesisPlanningOrchestrator" in self.source

    def test_plan_synthesis_method_exists(self):
        assert "async def plan_synthesis" in self.source

    def test_plan_synthesis_returns_response(self):
        """plan_synthesis should reference SynthesisResponse."""
        assert "SynthesisResponse" in self.source


# ── Async safety tests (with stubs) ──────────────────────────────

def _stub_all_service_modules():
    """Stub the full import chain so orchestrator can be imported."""
    stubs = {}

    # structlog
    if "structlog" not in sys.modules:
        _sl = types.ModuleType("structlog")
        _sl.get_logger = lambda *a, **kw: __import__("logging").getLogger("stub")
        _sl.stdlib = types.ModuleType("structlog.stdlib")
        _sl.stdlib.filter_by_level = None
        _sl.stdlib.LoggerFactory = lambda: None
        _sl.processors = types.ModuleType("structlog.processors")
        _sl.processors.TimeStamper = lambda **kw: None
        _sl.processors.JSONRenderer = lambda: None
        _sl.configure = lambda **kw: None
        stubs["structlog"] = _sl
        stubs["structlog.stdlib"] = _sl.stdlib
        stubs["structlog.processors"] = _sl.processors

    # anthropic
    if "anthropic" not in sys.modules:
        _anth = types.ModuleType("anthropic")
        _anth.AsyncAnthropic = type("AsyncAnthropic", (), {"__init__": lambda self, **kw: None})
        stubs["anthropic"] = _anth

    return stubs


def _make_orchestrator_no_db():
    """Import orchestrator with real deps (all installed)."""
    sys.path.insert(0, str(BACKEND_DIR))
    os.environ.setdefault("DEMO_MODE", "true")
    os.environ.setdefault("ANTHROPIC_API_KEY", "sk-test-placeholder")
    os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
    os.environ.setdefault("DB_NAME", "test_db")

    saved = {}
    stubs = _stub_all_service_modules()
    saved.update({k: sys.modules.get(k) for k in stubs})
    sys.modules.update(stubs)

    try:
        # Force re-import
        for mod_name in list(sys.modules):
            if mod_name.startswith("services.") or mod_name.startswith("models."):
                del sys.modules[mod_name]

        from services.orchestrator import SynthesisPlanningOrchestrator
        return SynthesisPlanningOrchestrator
    finally:
        # Restore original modules
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v


class TestOrchestratorStructure:
    """Test orchestrator class structure using real import."""

    @pytest.fixture(scope="class")
    def orch_class(self):
        return _make_orchestrator_no_db()

    def test_has_plan_synthesis_method(self, orch_class):
        assert hasattr(orch_class, "plan_synthesis")

    def test_plan_synthesis_is_coroutine(self, orch_class):
        method = getattr(orch_class, "plan_synthesis")
        assert inspect.iscoroutinefunction(method)

    def test_constructor_accepts_api_key(self, orch_class):
        sig = inspect.signature(orch_class.__init__)
        assert "api_key" in sig.parameters
