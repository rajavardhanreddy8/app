import React, { useState } from "react";
import axios from "axios";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Input } from "@/components/ui/input";
import {
  FlaskConical,
  Loader2,
  AlertCircle,
  CheckCircle2,
  TrendingUp,
  DollarSign,
  Target,
  ArrowRight,
  AlertTriangle,
  XCircle,
  Timer,
  Beaker,
  ChevronDown,
  ChevronUp,
} from "lucide-react";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const lowYieldRoute = {
  steps: [
    { reaction_type: "grignard", conditions: { catalyst: "None", solvent: "hexane", temperature_celsius: 200 }},
    { reaction_type: "friedel_crafts", conditions: { catalyst: "AlCl3", solvent: "benzene", temperature_celsius: 150 }},
  ],
  overall_yield_percent: 40,
  total_cost_usd: 300,
  num_steps: 2,
};

const moderateYieldRoute = {
  steps: [
    { reaction_type: "esterification", conditions: { catalyst: "H2SO4", solvent: "DCM", temperature_celsius: 120 }},
    { reaction_type: "suzuki_coupling", conditions: { catalyst: "Pd(OAc)2", solvent: "DMF", temperature_celsius: 100 }},
  ],
  overall_yield_percent: 65,
  total_cost_usd: 250,
  num_steps: 2,
};

const highYieldRoute = {
  steps: [
    { reaction_type: "hydrogenation", conditions: { catalyst: "Pd/C", solvent: "THF", temperature_celsius: 50 }},
  ],
  overall_yield_percent: 95,
  total_cost_usd: 200,
  num_steps: 1,
};

const YieldOptimizerPage = () => {
  const [routeJson, setRouteJson] = useState(JSON.stringify(lowYieldRoute, null, 2));
  const [pharmaMode, setPharmaMode] = useState(false);
  const [maxIter, setMaxIter] = useState(5);
  const [targetYield, setTargetYield] = useState(0.99);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [showHistory, setShowHistory] = useState(true);

  const presets = [
    { name: "Low yield (40%)", route: lowYieldRoute },
    { name: "Moderate (65%)", route: moderateYieldRoute },
    { name: "High yield (95%)", route: highYieldRoute },
  ];

  const optimize = async () => {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const route = JSON.parse(routeJson);
      const response = await axios.post(`${API}/routes/yield-optimize`, {
        route,
        pharma_mode: pharmaMode,
        max_iterations: maxIter,
        target_yield: targetYield,
      });
      setResult(response.data);
    } catch (e) {
      setError(e.response?.data?.detail || "Yield optimization failed.");
    } finally {
      setLoading(false);
    }
  };

  const getStatusConfig = (status) => {
    const map = {
      target_achieved: { color: "bg-green-600/30 text-green-300", icon: CheckCircle2, text: "Target Achieved!" },
      improved: { color: "bg-blue-600/30 text-blue-300", icon: TrendingUp, text: "Improved" },
      pharma_rejected: { color: "bg-red-600/30 text-red-300", icon: XCircle, text: "Pharma Rejected" },
      max_iterations: { color: "bg-yellow-600/30 text-yellow-300", icon: AlertTriangle, text: "Max Iterations" },
    };
    return map[status] || map.max_iterations;
  };

  const YieldBar = ({ value, target, label }) => {
    const pct = Math.min(value * 100, 100);
    const targetPct = target * 100;
    let color = "bg-green-500";
    if (pct < 70) color = "bg-red-500";
    else if (pct < 90) color = "bg-yellow-500";
    else if (pct < 99) color = "bg-blue-500";
    return (
      <div className="space-y-1">
        <div className="flex justify-between text-xs">
          <span className="text-purple-300/70">{label}</span>
          <span className="text-white font-mono font-bold">{pct.toFixed(1)}%</span>
        </div>
        <div className="relative w-full bg-white/10 rounded-full h-3">
          <div className={`${color} h-3 rounded-full transition-all duration-700`} style={{ width: `${pct}%` }} />
          {/* Target marker */}
          <div className="absolute top-0 h-3 w-0.5 bg-white/60" style={{ left: `${targetPct}%` }} />
        </div>
      </div>
    );
  };

  const YieldGauge = ({ value }) => {
    const pct = Math.min(value * 100, 100);
    let color = "text-red-400";
    let bg = "from-red-500 to-red-600";
    if (pct >= 99) { color = "text-green-400"; bg = "from-green-500 to-emerald-500"; }
    else if (pct >= 90) { color = "text-blue-400"; bg = "from-blue-500 to-cyan-500"; }
    else if (pct >= 70) { color = "text-yellow-400"; bg = "from-yellow-500 to-amber-500"; }

    return (
      <div className="text-center">
        <div className={`text-5xl font-bold ${color} font-mono`}>
          {pct.toFixed(1)}%
        </div>
        <div className={`mt-2 h-2 rounded-full bg-gradient-to-r ${bg} mx-auto`} style={{ width: `${Math.max(20, pct)}%` }} />
      </div>
    );
  };

  return (
    <div className="max-w-6xl mx-auto">
      <div className="flex items-center gap-3 mb-6">
        <FlaskConical className="w-8 h-8 text-purple-400" />
        <div>
          <h1 className="text-3xl font-bold text-white">Yield Optimizer</h1>
          <p className="text-purple-200/70 text-sm">
            Engineer yield to ≥99% — don't predict it, achieve it
          </p>
        </div>
      </div>

      {/* Input */}
      <Card className="bg-white/5 backdrop-blur-md border-purple-500/20 mb-6">
        <CardContent className="p-6 space-y-4">
          <div className="flex items-center justify-between mb-1">
            <label className="text-white font-medium">Route (JSON)</label>
            <div className="flex gap-2">
              {presets.map((p) => (
                <Button
                  key={p.name}
                  onClick={() => setRouteJson(JSON.stringify(p.route, null, 2))}
                  variant="outline"
                  size="sm"
                  className="bg-purple-500/10 border-purple-500/30 text-purple-200 text-xs"
                >
                  {p.name}
                </Button>
              ))}
            </div>
          </div>
          <textarea
            value={routeJson}
            onChange={(e) => setRouteJson(e.target.value)}
            rows={8}
            className="w-full bg-white/10 border border-purple-500/30 rounded-md p-3 text-white font-mono text-xs"
          />

          <div className="grid grid-cols-4 gap-4">
            <div>
              <label className="text-purple-200/70 text-xs mb-1 block">Target Yield</label>
              <Input
                type="number"
                step={0.01}
                min={0.5}
                max={1.0}
                value={targetYield}
                onChange={(e) => setTargetYield(parseFloat(e.target.value) || 0.99)}
                className="bg-white/10 border-purple-500/30 text-white text-sm"
              />
            </div>
            <div>
              <label className="text-purple-200/70 text-xs mb-1 block">Max Iterations</label>
              <Input
                type="number"
                min={1}
                max={10}
                value={maxIter}
                onChange={(e) => setMaxIter(parseInt(e.target.value) || 5)}
                className="bg-white/10 border-purple-500/30 text-white text-sm"
              />
            </div>
            <div className="flex items-end col-span-2">
              <label className="flex items-center gap-2 text-purple-200/70 text-sm cursor-pointer pb-2">
                <input
                  type="checkbox"
                  checked={pharmaMode}
                  onChange={(e) => setPharmaMode(e.target.checked)}
                  className="rounded border-purple-500/30 w-4 h-4"
                />
                <span className="flex items-center gap-1">
                  <FlaskConical className="w-4 h-4 text-blue-400" />
                  Pharma Mode (hard reject &lt;99%)
                </span>
              </label>
            </div>
          </div>

          <Button
            onClick={optimize}
            disabled={loading}
            className="w-full bg-gradient-to-r from-green-600 to-emerald-600 text-white text-lg py-6"
          >
            {loading ? (
              <><Loader2 className="w-5 h-5 animate-spin mr-2" /> Engineering Yield...</>
            ) : (
              <><Target className="w-5 h-5 mr-2" /> Optimize to {(targetYield*100).toFixed(0)}% Yield</>
            )}
          </Button>
        </CardContent>
      </Card>

      {error && (
        <Alert className="mb-6 bg-red-500/20 border-red-500/50">
          <AlertCircle className="h-4 w-4 text-red-400" />
          <AlertDescription className="text-red-200">{error}</AlertDescription>
        </Alert>
      )}

      {/* Results */}
      {result && (
        <div className="space-y-6">
          {/* Big yield gauge */}
          <Card className="bg-white/5 backdrop-blur-md border-purple-500/20">
            <CardContent className="p-8">
              <div className="flex items-center justify-between mb-6">
                <div className="flex items-center gap-3">
                  {(() => {
                    const sc = getStatusConfig(result.status);
                    const Icon = sc.icon;
                    return (
                      <Badge className={`${sc.color} text-sm gap-1`}>
                        <Icon className="w-4 h-4" /> {sc.text}
                      </Badge>
                    );
                  })()}
                  {result.pharma_mode && (
                    <Badge className={`${result.pharma_compliant ? 'bg-green-600/30 text-green-300' : 'bg-red-600/30 text-red-300'} text-xs`}>
                      Pharma: {result.pharma_compliant ? 'Compliant' : 'Non-compliant'}
                    </Badge>
                  )}
                </div>
                <div className="flex items-center gap-2 text-purple-300/60 text-sm">
                  <Timer className="w-4 h-4" />
                  {result.duration_ms}ms · {result.iterations_used} iterations
                </div>
              </div>

              {/* Yield comparison */}
              <div className="grid grid-cols-3 gap-8 mb-6">
                <div className="text-center">
                  <p className="text-purple-300/60 text-sm mb-2">Initial Yield</p>
                  <p className="text-4xl font-bold text-white font-mono">
                    {(result.initial_yield * 100).toFixed(1)}%
                  </p>
                </div>
                <div className="text-center flex flex-col items-center justify-center">
                  <ArrowRight className="w-8 h-8 text-green-400" />
                  <span className={`text-lg font-bold font-mono ${result.yield_improvement > 0 ? 'text-green-400' : 'text-yellow-400'}`}>
                    +{result.yield_improvement_pct}%
                  </span>
                </div>
                <div className="text-center">
                  <p className="text-purple-300/60 text-sm mb-2">Final Yield</p>
                  <YieldGauge value={result.final_yield} />
                </div>
              </div>

              {/* Target bar */}
              <YieldBar value={result.final_yield} target={result.target_yield} label={`Target: ${(result.target_yield*100).toFixed(0)}%`} />
            </CardContent>
          </Card>

          {/* Per-step yields */}
          <Card className="bg-white/5 backdrop-blur-md border-purple-500/20">
            <CardHeader>
              <CardTitle className="text-white">Per-Step Yield Breakdown</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-purple-200/60 text-xs mb-4">
                Y_total = y₁ × y₂ × y₃ × ... (multiplicative yield collapse)
              </p>
              <div className="space-y-3">
                {result.step_yields.map((s, i) => (
                  <div key={i} className={`rounded-lg p-4 border ${
                    i === result.yield_bottleneck_step
                      ? 'bg-red-500/10 border-red-500/30'
                      : 'bg-white/5 border-purple-500/20'
                  }`}>
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-2">
                        <Beaker className="w-4 h-4 text-purple-400" />
                        <span className="text-white font-semibold text-sm">
                          Step {s.step + 1}: {s.reaction_type}
                        </span>
                        {i === result.yield_bottleneck_step && (
                          <Badge className="bg-red-600/30 text-red-300 text-xs">Bottleneck</Badge>
                        )}
                      </div>
                      <span className={`font-mono font-bold ${
                        s.yield >= 0.99 ? 'text-green-400' :
                        s.yield >= 0.95 ? 'text-blue-400' :
                        s.yield >= 0.80 ? 'text-yellow-400' : 'text-red-400'
                      }`}>
                        {(s.yield * 100).toFixed(1)}%
                      </span>
                    </div>
                    <YieldBar value={s.yield} target={0.95} label="" />
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>

          {/* Cost impact */}
          <Card className="bg-white/5 backdrop-blur-md border-purple-500/20">
            <CardHeader>
              <CardTitle className="text-white flex items-center gap-2">
                <DollarSign className="w-5 h-5 text-yellow-400" />
                Loss-Based Cost Analysis
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-purple-200/60 text-xs mb-4">
                loss_cost = (1 - yield) × raw_material_cost — low yield = expensive
              </p>
              <div className="grid grid-cols-3 gap-4 mb-4">
                <div className="bg-white/5 rounded-lg p-4 border border-purple-500/20 text-center">
                  <p className="text-purple-300/60 text-xs">Loss Cost (Before)</p>
                  <p className="text-2xl font-bold text-red-400">
                    ${result.cost_analysis.loss_cost_initial}
                  </p>
                </div>
                <div className="bg-white/5 rounded-lg p-4 border border-purple-500/20 text-center">
                  <p className="text-purple-300/60 text-xs">Loss Cost (After)</p>
                  <p className="text-2xl font-bold text-green-400">
                    ${result.cost_analysis.loss_cost_final}
                  </p>
                </div>
                <div className="bg-white/5 rounded-lg p-4 border border-purple-500/20 text-center">
                  <p className="text-purple-300/60 text-xs">Saved from Yield</p>
                  <p className="text-2xl font-bold text-green-400">
                    ${result.cost_analysis.cost_saving_from_yield}
                  </p>
                </div>
              </div>

              {/* Scoring */}
              <div className="grid grid-cols-2 gap-4">
                <div className="bg-white/5 rounded-lg p-4 border border-purple-500/20 text-center">
                  <p className="text-purple-300/60 text-xs">Score Before</p>
                  <p className="text-xl font-bold text-white">{result.scoring.initial_score}</p>
                </div>
                <div className="bg-white/5 rounded-lg p-4 border border-purple-500/20 text-center">
                  <p className="text-purple-300/60 text-xs">Score After</p>
                  <p className="text-xl font-bold text-green-400">{result.scoring.final_score}</p>
                </div>
              </div>
              <p className="text-purple-300/50 text-xs text-center mt-2 font-mono">
                {result.scoring.score_formula}
              </p>
            </CardContent>
          </Card>

          {/* Optimization History */}
          <Card className="bg-white/5 backdrop-blur-md border-purple-500/20">
            <button
              onClick={() => setShowHistory(!showHistory)}
              className="w-full p-4 flex items-center justify-between text-left"
            >
              <CardTitle className="text-white">
                Optimization History ({result.iterations_used} iterations)
              </CardTitle>
              {showHistory ? <ChevronUp className="w-5 h-5 text-purple-300" /> : <ChevronDown className="w-5 h-5 text-purple-300" />}
            </button>
            {showHistory && (
              <CardContent className="pt-0 space-y-3">
                {result.optimization_history.map((h, i) => (
                  <div key={i} className="bg-white/5 rounded-lg p-4 border border-purple-500/20">
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-3">
                        <Badge className="bg-purple-600/30 text-purple-200">Iter {h.iteration}</Badge>
                        <span className="text-white font-mono text-sm">
                          {(h.yield_before * 100).toFixed(1)}%
                        </span>
                        <ArrowRight className="w-4 h-4 text-purple-400" />
                        <span className={`font-mono text-sm font-bold ${h.improvement > 0 ? 'text-green-400' : 'text-yellow-400'}`}>
                          {(h.yield_after * 100).toFixed(1)}%
                        </span>
                        <span className={`text-xs font-mono ${h.improvement > 0 ? 'text-green-400' : 'text-purple-300/50'}`}>
                          ({h.improvement > 0 ? '+' : ''}{(h.improvement * 100).toFixed(2)}%)
                        </span>
                      </div>
                      <span className="text-purple-300/50 text-xs">{h.duration_ms}ms</span>
                    </div>
                    {h.mutations && h.mutations.length > 0 && (
                      <div className="space-y-1 mt-2">
                        {h.mutations.map((m, mi) => (
                          <div key={mi} className="text-xs text-blue-200 bg-blue-500/10 px-2 py-1 rounded">
                            {m}
                          </div>
                        ))}
                      </div>
                    )}
                    {h.action === "target_achieved" && (
                      <div className="mt-2 flex items-center gap-1 text-green-300 text-sm">
                        <CheckCircle2 className="w-4 h-4" /> Target yield achieved!
                      </div>
                    )}
                  </div>
                ))}
              </CardContent>
            )}
          </Card>
        </div>
      )}
    </div>
  );
};

export default YieldOptimizerPage;
