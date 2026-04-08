import React, { useState } from "react";
import axios from "axios";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Separator } from "@/components/ui/separator";
import {
  Scale,
  Loader2,
  AlertCircle,
  DollarSign,
  TrendingUp,
  Factory,
  Beaker,
  Truck,
  BarChart3,
} from "lucide-react";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const ScaleUpPage = () => {
  const [activeTab, setActiveTab] = useState("scale");
  
  // Scale optimization state
  const [scaleReaction, setScaleReaction] = useState(JSON.stringify({
    reactants: ["CC(=O)O", "c1ccc(O)cc1"],
    products: ["CC(=O)Oc1ccccc1"],
    reaction_type: "esterification",
    temperature_celsius: 80,
    solvent: "acetic_anhydride",
    catalyst: "H2SO4"
  }, null, 2));
  const [targetScale, setTargetScale] = useState("pilot");
  const [batchSize, setBatchSize] = useState(10);
  const [scaleResult, setScaleResult] = useState(null);
  const [scaleLoading, setScaleLoading] = useState(false);
  const [scaleError, setScaleError] = useState(null);

  // Cost state
  const [costReaction, setCostReaction] = useState(JSON.stringify({
    reactants: ["CC(=O)O", "c1ccc(O)cc1"],
    products: ["CC(=O)Oc1ccccc1"],
    reaction_type: "esterification",
    temperature_celsius: 80,
    solvent: "acetic_anhydride"
  }, null, 2));
  const [costScale, setCostScale] = useState("lab");
  const [costBatchSize, setCostBatchSize] = useState(0.1);
  const [includeRecovery, setIncludeRecovery] = useState(false);
  const [costResult, setCostResult] = useState(null);
  const [costLoading, setCostLoading] = useState(false);
  const [costError, setCostError] = useState(null);

  // Constraints state
  const [constraintResult, setConstraintResult] = useState(null);
  const [constraintLoading, setConstraintLoading] = useState(false);
  const [constraintError, setConstraintError] = useState(null);

  const optimizeScale = async () => {
    setScaleLoading(true);
    setScaleError(null);
    try {
      const reaction = JSON.parse(scaleReaction);
      const response = await axios.post(`${API}/scale/optimize`, {
        reaction,
        target_scale: targetScale,
        batch_size_kg: batchSize,
      });
      setScaleResult(response.data);
    } catch (e) {
      console.error("Scale error:", e);
      setScaleError(e.response?.data?.detail || "Failed to optimize. Check JSON input.");
    } finally {
      setScaleLoading(false);
    }
  };

  const calculateCost = async () => {
    setCostLoading(true);
    setCostError(null);
    try {
      const reaction = JSON.parse(costReaction);
      const response = await axios.post(`${API}/cost/industrial`, {
        reaction,
        scale: costScale,
        batch_size_kg: costBatchSize,
        include_recovery: includeRecovery,
      });
      setCostResult(response.data);
    } catch (e) {
      console.error("Cost error:", e);
      setCostError(e.response?.data?.detail || "Failed to calculate. Check JSON.");
    } finally {
      setCostLoading(false);
    }
  };

  const evaluateConstraints = async () => {
    setConstraintLoading(true);
    setConstraintError(null);
    try {
      const reaction = JSON.parse(scaleReaction);
      const response = await axios.post(`${API}/constraints/evaluate`, {
        reaction,
        scale: targetScale,
        batch_size_kg: batchSize,
      });
      setConstraintResult(response.data);
    } catch (e) {
      console.error("Constraint error:", e);
      setConstraintError(e.response?.data?.detail || "Failed to evaluate constraints.");
    } finally {
      setConstraintLoading(false);
    }
  };

  const getRiskColor = (risk) => {
    if (!risk) return "text-gray-400";
    const r = risk.toLowerCase();
    if (r.includes("low") || r.includes("good")) return "text-green-400";
    if (r.includes("medium") || r.includes("moderate")) return "text-yellow-400";
    return "text-red-400";
  };

  const getScoreBar = (score, max = 1) => {
    const pct = Math.min((score / max) * 100, 100);
    let color = "bg-green-500";
    if (pct > 60) color = "bg-red-500";
    else if (pct > 30) color = "bg-yellow-500";
    return (
      <div className="w-full bg-white/10 rounded-full h-2">
        <div className={`${color} h-2 rounded-full transition-all`} style={{ width: `${pct}%` }} />
      </div>
    );
  };

  return (
    <div className="max-w-6xl mx-auto">
      <div className="flex items-center gap-3 mb-6">
        <Scale className="w-8 h-8 text-purple-400" />
        <div>
          <h1 className="text-3xl font-bold text-white">Scale-Up & Cost Analysis</h1>
          <p className="text-purple-200/70 text-sm">
            Industrial optimization, cost modeling & process constraints
          </p>
        </div>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="bg-white/5 border border-purple-500/20 mb-6">
          <TabsTrigger value="scale" className="data-[state=active]:bg-purple-600/30 text-purple-200">
            <Factory className="w-4 h-4 mr-2" /> Scale Optimization
          </TabsTrigger>
          <TabsTrigger value="cost" className="data-[state=active]:bg-purple-600/30 text-purple-200">
            <DollarSign className="w-4 h-4 mr-2" /> Cost Analysis
          </TabsTrigger>
          <TabsTrigger value="constraints" className="data-[state=active]:bg-purple-600/30 text-purple-200">
            <BarChart3 className="w-4 h-4 mr-2" /> Process Constraints
          </TabsTrigger>
        </TabsList>

        {/* Scale Tab */}
        <TabsContent value="scale">
          <Card className="bg-white/5 backdrop-blur-md border-purple-500/20 mb-6">
            <CardContent className="p-6 space-y-4">
              <div>
                <label className="text-white font-medium mb-2 block">Reaction (JSON)</label>
                <textarea
                  value={scaleReaction}
                  onChange={(e) => setScaleReaction(e.target.value)}
                  rows={6}
                  className="w-full bg-white/10 border border-purple-500/30 rounded-md p-3 text-white font-mono text-xs"
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="text-purple-200/70 text-xs mb-1 block">Target Scale</label>
                  <select
                    value={targetScale}
                    onChange={(e) => setTargetScale(e.target.value)}
                    className="w-full bg-white/10 border border-purple-500/30 rounded-md px-3 py-2 text-white text-sm"
                  >
                    <option value="lab" className="bg-slate-800">Lab (0.001-1 kg)</option>
                    <option value="pilot" className="bg-slate-800">Pilot (1-100 kg)</option>
                    <option value="industrial" className="bg-slate-800">Industrial (100+ kg)</option>
                  </select>
                </div>
                <div>
                  <label className="text-purple-200/70 text-xs mb-1 block">Batch Size (kg)</label>
                  <Input
                    type="number"
                    value={batchSize}
                    onChange={(e) => setBatchSize(parseFloat(e.target.value))}
                    className="bg-white/10 border-purple-500/30 text-white"
                  />
                </div>
              </div>
              <Button
                onClick={optimizeScale}
                disabled={scaleLoading}
                className="w-full bg-gradient-to-r from-purple-600 to-pink-600 text-white"
              >
                {scaleLoading ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : <Factory className="w-4 h-4 mr-2" />}
                Optimize for Scale
              </Button>
            </CardContent>
          </Card>

          {scaleError && (
            <Alert className="mb-4 bg-red-500/20 border-red-500/50">
              <AlertCircle className="h-4 w-4 text-red-400" />
              <AlertDescription className="text-red-200">{scaleError}</AlertDescription>
            </Alert>
          )}

          {scaleResult && (
            <Card className="bg-white/5 backdrop-blur-md border-purple-500/20">
              <CardHeader>
                <CardTitle className="text-white">Scale Optimization Results</CardTitle>
              </CardHeader>
              <CardContent>
                <pre className="text-purple-200 text-xs font-mono bg-slate-800/50 p-4 rounded-lg overflow-auto max-h-96">
                  {JSON.stringify(scaleResult, null, 2)}
                </pre>
              </CardContent>
            </Card>
          )}
        </TabsContent>

        {/* Cost Tab */}
        <TabsContent value="cost">
          <Card className="bg-white/5 backdrop-blur-md border-purple-500/20 mb-6">
            <CardContent className="p-6 space-y-4">
              <div>
                <label className="text-white font-medium mb-2 block">Reaction (JSON)</label>
                <textarea
                  value={costReaction}
                  onChange={(e) => setCostReaction(e.target.value)}
                  rows={6}
                  className="w-full bg-white/10 border border-purple-500/30 rounded-md p-3 text-white font-mono text-xs"
                />
              </div>
              <div className="grid grid-cols-3 gap-4">
                <div>
                  <label className="text-purple-200/70 text-xs mb-1 block">Scale</label>
                  <select
                    value={costScale}
                    onChange={(e) => setCostScale(e.target.value)}
                    className="w-full bg-white/10 border border-purple-500/30 rounded-md px-3 py-2 text-white text-sm"
                  >
                    <option value="lab" className="bg-slate-800">Lab</option>
                    <option value="pilot" className="bg-slate-800">Pilot</option>
                    <option value="industrial" className="bg-slate-800">Industrial</option>
                  </select>
                </div>
                <div>
                  <label className="text-purple-200/70 text-xs mb-1 block">Batch Size (kg)</label>
                  <Input
                    type="number"
                    value={costBatchSize}
                    onChange={(e) => setCostBatchSize(parseFloat(e.target.value))}
                    className="bg-white/10 border-purple-500/30 text-white"
                  />
                </div>
                <div className="flex items-end">
                  <label className="flex items-center gap-2 text-purple-200/70 text-sm cursor-pointer">
                    <input
                      type="checkbox"
                      checked={includeRecovery}
                      onChange={(e) => setIncludeRecovery(e.target.checked)}
                      className="rounded border-purple-500/30"
                    />
                    Include Recovery
                  </label>
                </div>
              </div>
              <Button
                onClick={calculateCost}
                disabled={costLoading}
                className="w-full bg-gradient-to-r from-green-600 to-emerald-600 text-white"
              >
                {costLoading ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : <DollarSign className="w-4 h-4 mr-2" />}
                Calculate Industrial Cost
              </Button>
            </CardContent>
          </Card>

          {costError && (
            <Alert className="mb-4 bg-red-500/20 border-red-500/50">
              <AlertCircle className="h-4 w-4 text-red-400" />
              <AlertDescription className="text-red-200">{costError}</AlertDescription>
            </Alert>
          )}

          {costResult && (
            <Card className="bg-white/5 backdrop-blur-md border-purple-500/20">
              <CardHeader>
                <CardTitle className="text-white">Cost Breakdown</CardTitle>
              </CardHeader>
              <CardContent>
                <pre className="text-purple-200 text-xs font-mono bg-slate-800/50 p-4 rounded-lg overflow-auto max-h-96">
                  {JSON.stringify(costResult, null, 2)}
                </pre>
              </CardContent>
            </Card>
          )}
        </TabsContent>

        {/* Constraints Tab */}
        <TabsContent value="constraints">
          <Card className="bg-white/5 backdrop-blur-md border-purple-500/20 mb-6">
            <CardContent className="p-6 space-y-4">
              <p className="text-purple-200/70 text-sm">
                Evaluates thermal, mixing, mass transfer, safety, and purification constraints
                using the reaction data from the Scale tab.
              </p>
              <Button
                onClick={evaluateConstraints}
                disabled={constraintLoading}
                className="w-full bg-gradient-to-r from-orange-600 to-red-600 text-white"
              >
                {constraintLoading ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : <BarChart3 className="w-4 h-4 mr-2" />}
                Evaluate Process Constraints
              </Button>
            </CardContent>
          </Card>

          {constraintError && (
            <Alert className="mb-4 bg-red-500/20 border-red-500/50">
              <AlertCircle className="h-4 w-4 text-red-400" />
              <AlertDescription className="text-red-200">{constraintError}</AlertDescription>
            </Alert>
          )}

          {constraintResult && constraintResult.constraints && (
            <Card className="bg-white/5 backdrop-blur-md border-purple-500/20">
              <CardHeader>
                <CardTitle className="text-white">Process Constraints Analysis</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                {/* Constraint Scores */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {[
                    { label: "Heat Risk", risk: constraintResult.constraints.heat_risk, score: constraintResult.constraints.heat_score },
                    { label: "Mixing Efficiency", risk: constraintResult.constraints.mixing_efficiency, score: constraintResult.constraints.mixing_score },
                    { label: "Mass Transfer", risk: constraintResult.constraints.mass_transfer, score: constraintResult.constraints.mass_transfer_score },
                    { label: "Safety Risk", risk: constraintResult.constraints.safety_risk, score: constraintResult.constraints.safety_score },
                    { label: "Purification", risk: constraintResult.constraints.purification_difficulty, score: constraintResult.constraints.purification_score },
                  ].map((item, i) => (
                    <div key={i} className="bg-white/5 rounded-lg p-4 border border-purple-500/20">
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-white font-medium text-sm">{item.label}</span>
                        <span className={`text-sm font-semibold ${getRiskColor(item.risk)}`}>
                          {item.risk || "N/A"}
                        </span>
                      </div>
                      {getScoreBar(item.score || 0)}
                      <span className="text-purple-300/50 text-xs">Score: {item.score?.toFixed(2) || 0}</span>
                    </div>
                  ))}
                </div>

                {/* Total Penalty */}
                <div className="bg-white/5 rounded-lg p-4 border border-purple-500/20 text-center">
                  <span className="text-purple-300/70 text-sm">Total Penalty</span>
                  <p className="text-3xl font-bold text-white">
                    {constraintResult.constraints.total_penalty?.toFixed(2) || 0}
                  </p>
                </div>

                {/* Recommendations */}
                {constraintResult.recommendations && constraintResult.recommendations.length > 0 && (
                  <div>
                    <h3 className="text-white font-semibold mb-2">Recommendations</h3>
                    <div className="space-y-2">
                      {constraintResult.recommendations.map((rec, i) => (
                        <div key={i} className="bg-blue-500/10 rounded-lg p-3 border border-blue-500/20">
                          <p className="text-blue-200 text-sm">{rec}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Equipment */}
                {constraintResult.equipment_requirements && constraintResult.equipment_requirements.length > 0 && (
                  <div>
                    <h3 className="text-white font-semibold mb-2">Equipment Requirements</h3>
                    <div className="flex flex-wrap gap-2">
                      {constraintResult.equipment_requirements.map((eq, i) => (
                        <Badge key={i} variant="outline" className="border-purple-500/30 text-purple-200">
                          {eq}
                        </Badge>
                      ))}
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
};

export default ScaleUpPage;
