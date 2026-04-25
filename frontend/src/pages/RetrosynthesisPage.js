import React, { useState } from "react";
import axios from "axios";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription } from "@/components/ui/alert";
import SmilesInput from "../components/SmilesInput";
import MoleculeRenderer from "../components/MoleculeRenderer";
import {
  GitBranch,
  Loader2,
  AlertCircle,
  ChevronDown,
  ChevronUp,
  ArrowDown,
  Beaker,
  Layers,
  Network,
  List,
} from "lucide-react";
import RetrosynthesisTree from "../components/RetrosynthesisTree";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const exampleMolecules = [
  { name: "Aspirin",     smiles: "CC(=O)Oc1ccccc1C(=O)O" },
  { name: "Ibuprofen",   smiles: "CC(C)Cc1ccc(cc1)C(C)C(=O)O" },
  { name: "Paracetamol", smiles: "CC(=O)Nc1ccc(O)cc1" },
];

const RetrosynthesisPage = () => {
  const [targetSmiles,  setTargetSmiles]  = useState("");
  const [maxDepth,      setMaxDepth]      = useState(5);
  const [maxRoutes,     setMaxRoutes]     = useState(5);
  const [loading,       setLoading]       = useState(false);
  const [result,        setResult]        = useState(null);
  const [error,         setError]         = useState(null);
  const [expandedRoute, setExpandedRoute] = useState(0);
  // "tree" | "table"
  const [viewMode,      setViewMode]      = useState("tree");
  // which route the tree highlights
  const [selectedRoute, setSelectedRoute] = useState(0);

  const planRetrosynthesis = async (smilesInput) => {
    const target = smilesInput || targetSmiles;
    if (!target.trim()) { setError("Please enter a target SMILES"); return; }

    setLoading(true);
    setError(null);
    setResult(null);
    setSelectedRoute(0);

    try {
      const response = await axios.post(`${API}/retrosynthesis/plan`, {
        target_smiles: target,
        max_depth:     maxDepth,
        max_routes:    maxRoutes,
      });
      setResult(response.data);
    } catch (e) {
      console.error("Retrosynthesis error:", e);
      setError(e.response?.data?.detail || "Failed to generate retrosynthesis routes.");
    } finally {
      setLoading(false);
    }
  };

  // ── Table view: original text-card rendering ────────────────────────────
  const renderRouteTree = (route) => {
    if (!route) return null;
    const steps  = route.steps || route.disconnections || [];
    const target = route.target || route.target_smiles || targetSmiles;

    return (
      <div className="space-y-3">
        <div className="flex items-center gap-2">
          <div className="bg-purple-600/30 rounded-lg px-3 py-2 border border-purple-500/30">
            <code className="text-purple-200 text-sm font-mono">{target}</code>
          </div>
          <Badge className="bg-purple-600 text-white">Target</Badge>
        </div>

        {steps.map((step, idx) => (
          <div key={idx} className="ml-6">
            <div className="flex items-center gap-2 mb-2">
              <ArrowDown className="w-4 h-4 text-purple-400" />
              <span className="text-purple-300/60 text-xs">
                Step {idx + 1}: {step.reaction_type || step.transform || "Disconnection"}
              </span>
              {step.score && (
                <Badge variant="outline" className="border-purple-500/30 text-purple-300 text-xs">
                  Score: {typeof step.score === "number" ? step.score.toFixed(2) : step.score}
                </Badge>
              )}
            </div>

            <div className="flex flex-wrap gap-2 ml-6">
              {(step.precursors || step.reactants || []).map((p, pIdx) => (
                <div
                  key={pIdx}
                  className="bg-blue-500/10 rounded-lg px-3 py-2 border border-blue-500/20"
                >
                  <code className="text-blue-200 text-xs font-mono">
                    {typeof p === "string" ? p : p.smiles || JSON.stringify(p)}
                  </code>
                </div>
              ))}
            </div>

            {step.conditions && (
              <div className="ml-6 mt-1 text-xs text-purple-300/50">
                {typeof step.conditions === "string"
                  ? step.conditions
                  : Object.entries(step.conditions)
                      .map(([k, v]) => (v ? `${k}: ${v}` : null))
                      .filter(Boolean)
                      .join(" | ")}
              </div>
            )}
          </div>
        ))}

        {steps.length === 0 && (
          <div className="ml-6 text-purple-300/40 text-sm italic">
            No disconnection steps available for this route
          </div>
        )}
      </div>
    );
  };

  const routes = result?.routes || [];

  return (
    <div className="max-w-6xl mx-auto">
      {/* ── Header ───────────────────────────────────────────────────────── */}
      <div className="flex items-center gap-3 mb-6">
        <GitBranch className="w-8 h-8 text-purple-400" />
        <div>
          <h1 className="text-3xl font-bold text-white">Retrosynthesis Explorer</h1>
          <p className="text-purple-200/70 text-sm">
            Tree-based retrosynthetic route analysis
          </p>
        </div>
      </div>

      {/* ── Input card ───────────────────────────────────────────────────── */}
      <Card className="bg-white/5 backdrop-blur-md border-purple-500/20 mb-6">
        <CardContent className="p-6 space-y-4">
          <SmilesInput
            id="retro-smiles-input"
            label="Target Molecule (SMILES)"
            value={targetSmiles}
            onChange={(v) => setTargetSmiles(v)}
            placeholder="e.g., CC(=O)Oc1ccccc1C(=O)O"
            previewSize={180}
            showPresets={false}
          />
          {/* Analyse button row */}
          <div style={{ display: "flex", justifyContent: "flex-end" }}>
            <Button
              onClick={() => planRetrosynthesis()}
              disabled={loading}
              className="bg-gradient-to-r from-blue-600 to-cyan-600 text-white px-8"
            >
              {loading ? (
                <><Loader2 className="w-4 h-4 animate-spin mr-2" />Analyzing…</>
              ) : (
                "Plan Routes"
              )}
            </Button>
          </div>

          <div className="flex flex-wrap gap-2">
            {exampleMolecules.map((mol) => (
              <Button
                key={mol.name}
                onClick={() => { setTargetSmiles(mol.smiles); planRetrosynthesis(mol.smiles); }}
                variant="outline"
                size="sm"
                className="bg-purple-500/10 border-purple-500/30 text-purple-200 text-xs"
              >
                {mol.name}
              </Button>
            ))}
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-purple-200/70 text-xs mb-1 block">
                Max Depth: {maxDepth}
              </label>
              <Input
                type="range" min={1} max={10} value={maxDepth}
                onChange={(e) => setMaxDepth(parseInt(e.target.value))}
                className="bg-white/10"
              />
            </div>
            <div>
              <label className="text-purple-200/70 text-xs mb-1 block">
                Max Routes: {maxRoutes}
              </label>
              <Input
                type="range" min={1} max={10} value={maxRoutes}
                onChange={(e) => setMaxRoutes(parseInt(e.target.value))}
                className="bg-white/10"
              />
            </div>
          </div>
        </CardContent>
      </Card>

      {/* ── Error ────────────────────────────────────────────────────────── */}
      {error && (
        <Alert className="mb-6 bg-red-500/20 border-red-500/50">
          <AlertCircle className="h-4 w-4 text-red-400" />
          <AlertDescription className="text-red-200">{error}</AlertDescription>
        </Alert>
      )}

      {/* ── Results ──────────────────────────────────────────────────────── */}
      {result && (
        <div className="space-y-4">
          {/* Summary bar + view toggle */}
          <Card className="bg-white/5 backdrop-blur-md border-purple-500/20">
            <CardHeader>
              <div className="flex items-center justify-between flex-wrap gap-3">
                <CardTitle className="text-white">
                  Found {result.num_routes || routes.length || 0} Routes
                </CardTitle>

                <div className="flex items-center gap-3">
                  <Badge className="bg-blue-600 text-white">
                    Target: {result.target_smiles}
                  </Badge>

                  {/* View toggle */}
                  <div className="flex rounded-lg overflow-hidden border border-purple-500/30">
                    <button
                      onClick={() => setViewMode("tree")}
                      className={[
                        "flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium transition-colors",
                        viewMode === "tree"
                          ? "bg-purple-600 text-white"
                          : "bg-white/5 text-purple-300 hover:bg-purple-600/20",
                      ].join(" ")}
                    >
                      <Network className="w-3.5 h-3.5" /> Tree View
                    </button>
                    <button
                      onClick={() => setViewMode("table")}
                      className={[
                        "flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium transition-colors",
                        viewMode === "table"
                          ? "bg-purple-600 text-white"
                          : "bg-white/5 text-purple-300 hover:bg-purple-600/20",
                      ].join(" ")}
                    >
                      <List className="w-3.5 h-3.5" /> Table View
                    </button>
                  </div>
                </div>
              </div>
            </CardHeader>
          </Card>

          {/* ── Tree View ─────────────────────────────────────────────────── */}
          {viewMode === "tree" && routes.length > 0 && (
            <Card className="bg-white/5 backdrop-blur-md border-purple-500/20">
              <CardContent className="p-5">
                <RetrosynthesisTree
                  routes={routes}
                  selectedRoute={selectedRoute}
                  onRouteSelect={setSelectedRoute}
                />
              </CardContent>
            </Card>
          )}

          {viewMode === "tree" && routes.length === 0 && (
            <Card className="bg-white/5 backdrop-blur-md border-purple-500/20">
              <CardContent className="p-8 text-center text-purple-300/50 italic">
                No routes found — try increasing Max Depth or using a simpler molecule.
              </CardContent>
            </Card>
          )}

          {/* ── Table View ────────────────────────────────────────────────── */}
          {viewMode === "table" && routes.map((route, idx) => (
            <Card key={idx} className="bg-white/5 backdrop-blur-md border-purple-500/20">
              <CardContent className="p-0">
                <button
                  onClick={() => setExpandedRoute(expandedRoute === idx ? null : idx)}
                  className="w-full p-4 flex items-center justify-between text-left"
                >
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-full bg-blue-600/30 flex items-center justify-center">
                      <Layers className="w-4 h-4 text-blue-300" />
                    </div>
                    <div>
                      <span className="text-white font-semibold">Route {idx + 1}</span>
                      <span className="text-purple-300/60 text-xs ml-3">
                        {route.steps?.length || route.disconnections?.length || 0} steps
                      </span>
                    </div>
                    {route.total_score && (
                      <Badge variant="outline" className="border-green-500/30 text-green-300 text-xs">
                        Score: {route.total_score.toFixed(2)}
                      </Badge>
                    )}
                  </div>
                  {expandedRoute === idx
                    ? <ChevronUp className="w-5 h-5 text-purple-300" />
                    : <ChevronDown className="w-5 h-5 text-purple-300" />}
                </button>

                {expandedRoute === idx && (
                  <div className="px-4 pb-4 border-t border-purple-500/20 pt-4">
                    {renderRouteTree(route)}
                  </div>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
};

export default RetrosynthesisPage;
