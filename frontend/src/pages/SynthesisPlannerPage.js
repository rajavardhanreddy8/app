import React, { useState } from "react";
import axios from "axios";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Separator } from "@/components/ui/separator";
import { Loader2, Beaker, TrendingUp, DollarSign, Clock, AlertCircle, CheckCircle2 } from "lucide-react";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const SynthesisPlannerPage = () => {
  const [targetSmiles, setTargetSmiles] = useState("");
  const [maxSteps, setMaxSteps] = useState(5);
  const [optimizeFor, setOptimizeFor] = useState("balanced");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [validationResult, setValidationResult] = useState(null);
  
  // Phase 4: Advanced mode state
  const [useAdvanced, setUseAdvanced] = useState(false);
  const [scale, setScale] = useState("lab");
  const [batchSize, setBatchSize] = useState(0.1);
  const [expandedRoute, setExpandedRoute] = useState(null);

  const validateMolecule = async (smiles) => {
    if (!smiles) return;
    
    try {
      const response = await axios.post(`${API}/molecule/validate`, { smiles });
      setValidationResult(response.data);
      
      if (!response.data.valid) {
        setError(response.data.reason || "Invalid SMILES");
      } else {
        setError(null);
      }
    } catch (e) {
      console.error("Validation error:", e);
      setValidationResult({ valid: false, reason: "Validation failed" });
    }
  };

  const handlePlanSynthesis = async () => {
    if (!targetSmiles) {
      setError("Please enter a target SMILES");
      return;
    }

    setLoading(true);
    setError(null);
    setResult(null);

    try {
      // Build URL with advanced parameters
      const params = useAdvanced 
        ? `?use_advanced=true&scale=${scale}&batch_size_kg=${batchSize}`
        : '';
      
      const response = await axios.post(`${API}/synthesis/plan${params}`, {
        target_smiles: targetSmiles,
        max_steps: maxSteps,
        optimize_for: optimizeFor,
      });

      setResult(response.data);
    } catch (e) {
      console.error("Planning error:", e);
      setError(
        e.response?.data?.detail || "Failed to generate synthesis plan. Please check your input."
      );
    } finally {
      setLoading(false);
    }
  };

  const getDifficultyColor = (difficulty) => {
    switch (difficulty) {
      case "easy":
        return "bg-green-500";
      case "moderate":
        return "bg-yellow-500";
      case "high":
      case "difficult":
        return "bg-red-500";
      default:
        return "bg-gray-500";
    }
  };

  const exampleMolecules = [
    { name: "Aspirin", smiles: "CC(=O)Oc1ccccc1C(=O)O" },
    { name: "Caffeine", smiles: "CN1C=NC2=C1C(=O)N(C(=O)N2C)C" },
    { name: "Ibuprofen", smiles: "CC(C)Cc1ccc(cc1)C(C)C(=O)O" },
    { name: "Paracetamol", smiles: "CC(=O)Nc1ccc(O)cc1" },
  ];

  return (
    <div className="min-h-screen p-8">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="text-center mb-12">
          <div className="flex items-center justify-center mb-4">
            <Beaker className="w-12 h-12 text-purple-400 mr-4" />
            <h1 className="text-5xl font-bold text-white">
              AI Synthesis Planner
            </h1>
          </div>
          <p className="text-xl text-purple-200">
            Plan optimal chemical synthesis routes with AI-powered retrosynthetic analysis
          </p>
          <p className="text-sm text-purple-300 mt-2">
            Powered by Claude Sonnet 4.5 & RDKit
          </p>
        </div>

        {/* Input Section */}
        <Card className="mb-8 bg-white/10 backdrop-blur-md border-purple-500/30">
          <CardHeader>
            <CardTitle className="text-white">Target Molecule</CardTitle>
            <CardDescription className="text-purple-200">
              Enter the SMILES notation of your target molecule
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            {/* SMILES Input */}
            <div>
              <label className="text-white font-medium mb-2 block">
                SMILES String
              </label>
              <div className="flex gap-2">
                <Input
                  data-testid="smiles-input"
                  type="text"
                  placeholder="e.g., CC(=O)Oc1ccccc1C(=O)O"
                  value={targetSmiles}
                  onChange={(e) => {
                    setTargetSmiles(e.target.value);
                    setValidationResult(null);
                  }}
                  onBlur={() => validateMolecule(targetSmiles)}
                  className="flex-1 bg-white/20 border-purple-300/50 text-white placeholder:text-purple-300/50"
                />
                <Button
                  data-testid="validate-button"
                  onClick={() => validateMolecule(targetSmiles)}
                  variant="outline"
                  className="bg-purple-500/20 border-purple-400 text-white hover:bg-purple-500/30"
                >
                  Validate
                </Button>
              </div>
              
              {validationResult && (
                <div className="mt-2">
                  {validationResult.valid ? (
                    <Alert className="bg-green-500/20 border-green-500/50">
                      <CheckCircle2 className="h-4 w-4 text-green-400" />
                      <AlertDescription className="text-green-200">
                        Valid SMILES structure
                      </AlertDescription>
                    </Alert>
                  ) : (
                    <Alert className="bg-red-500/20 border-red-500/50">
                      <AlertCircle className="h-4 w-4 text-red-400" />
                      <AlertDescription className="text-red-200">
                        {validationResult.reason || "Invalid SMILES"}
                      </AlertDescription>
                    </Alert>
                  )}
                </div>
              )}
            </div>

            {/* Example Molecules */}
            <div>
              <label className="text-white font-medium mb-2 block">
                Or try an example:
              </label>
              <div className="flex flex-wrap gap-2">
                {exampleMolecules.map((mol) => (
                  <Button
                    key={mol.name}
                    onClick={() => {
                      setTargetSmiles(mol.smiles);
                      validateMolecule(mol.smiles);
                    }}
                    variant="outline"
                    size="sm"
                    className="bg-purple-500/20 border-purple-400/50 text-purple-200 hover:bg-purple-500/30"
                  >
                    {mol.name}
                  </Button>
                ))}
              </div>
            </div>


            <Separator className="bg-purple-500/30" />

            {/* Phase 4: Advanced Mode Toggle */}
            <div className="p-4 bg-purple-900/20 rounded-lg border border-purple-500/30">
              <div className="flex items-center justify-between mb-3">
                <label className="text-white font-medium">
                  🚀 Advanced Mode (Industrial Optimization)
                </label>
                <button
                  onClick={() => setUseAdvanced(!useAdvanced)}
                  className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                    useAdvanced ? 'bg-purple-600' : 'bg-gray-600'
                  }`}
                >
                  <span
                    className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                      useAdvanced ? 'translate-x-6' : 'translate-x-1'
                    }`}
                  />
                </button>
              </div>
              
              {useAdvanced && (
                <div className="space-y-3 pt-3 border-t border-purple-500/30">
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-xs text-purple-200 mb-1">Production Scale</label>
                      <select
                        value={scale}
                        onChange={(e) => setScale(e.target.value)}
                        className="w-full bg-purple-900/40 border border-purple-500/30 rounded px-3 py-2 text-sm text-white"
                      >
                        <option value="lab">Lab (0.001-1 kg)</option>
                        <option value="pilot">Pilot (1-100 kg)</option>
                        <option value="industrial">Industrial (100+ kg)</option>
                      </select>
                    </div>
                    
                    <div>
                      <label className="block text-xs text-purple-200 mb-1">Batch Size (kg)</label>
                      <Input
                        type="number"
                        value={batchSize}
                        onChange={(e) => setBatchSize(parseFloat(e.target.value))}
                        step={scale === 'lab' ? 0.1 : scale === 'pilot' ? 1 : 10}
                        min={scale === 'lab' ? 0.001 : scale === 'pilot' ? 1 : 100}
                        className="bg-purple-900/40 border-purple-500/30 text-white text-sm"
                      />
                    </div>
                  </div>
                  <p className="text-xs text-purple-300">
                    ✨ Uses ML retrosynthesis, scale optimization & industrial cost modeling
                  </p>
                </div>
              )}
            </div>

            {/* Options */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="text-white font-medium mb-2 block">
                  Max Steps: {maxSteps}
                </label>
                <Input
                  type="range"
                  min="1"
                  max="10"
                  value={maxSteps}
                  onChange={(e) => setMaxSteps(parseInt(e.target.value))}
                  className="bg-white/20"
                />
              </div>

              <div>
                <label className="text-white font-medium mb-2 block">
                  Optimize For
                </label>
                <select
                  data-testid="optimize-select"
                  value={optimizeFor}
                  onChange={(e) => setOptimizeFor(e.target.value)}
                  className="w-full p-2 rounded-md bg-white/20 border border-purple-300/50 text-white"
                >
                  <option value="balanced" className="bg-slate-800">Balanced</option>
                  <option value="yield" className="bg-slate-800">High Yield</option>
                  <option value="cost" className="bg-slate-800">Low Cost</option>
                  <option value="time" className="bg-slate-800">Fast (Few Steps)</option>
                </select>
              </div>
            </div>

            {/* Submit Button */}
            <Button
              data-testid="plan-button"
              onClick={handlePlanSynthesis}
              disabled={loading || !targetSmiles}
              className="w-full bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 text-white font-semibold py-6 text-lg"
            >
              {loading ? (
                <>
                  <Loader2 className="mr-2 h-5 w-5 animate-spin" />
                  Planning Synthesis Routes...
                </>
              ) : (
                "Generate Synthesis Plan"
              )}
            </Button>
          </CardContent>
        </Card>

        {/* Error Display */}
        {error && (
          <Alert className="mb-8 bg-red-500/20 border-red-500/50">
            <AlertCircle className="h-4 w-4 text-red-400" />
            <AlertDescription className="text-red-200">{error}</AlertDescription>
          </Alert>
        )}

        {/* Results Display */}
        {result && result.routes && result.routes.length > 0 && (
          <div className="space-y-6" data-testid="results-section">
            {/* Summary */}
            <Card className="bg-white/10 backdrop-blur-md border-purple-500/30">
              <CardHeader>
                <CardTitle className="text-white">Results Summary</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-center">
                  <div>
                    <p className="text-purple-300 text-sm">Routes Found</p>
                    <p className="text-3xl font-bold text-white">{result.routes.length}</p>
                  </div>
                  <div>
                    <p className="text-purple-300 text-sm">Computation Time</p>
                    <p className="text-3xl font-bold text-white">{result.computation_time_seconds}s</p>
                  </div>
                  <div>
                    <p className="text-purple-300 text-sm">Tokens Used</p>
                    <p className="text-3xl font-bold text-white">{result.tokens_used}</p>
                  </div>
                  <div>
                    <p className="text-purple-300 text-sm">Target</p>
                    <p className="text-sm font-mono text-white truncate">{result.target_smiles}</p>
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Routes */}
            <div className="space-y-4">
              <h2 className="text-2xl font-bold text-white">Synthesis Routes</h2>
              {result.routes.map((route, routeIdx) => (
                <Card
                  key={route.id}
                  className="bg-white/10 backdrop-blur-md border-purple-500/30"
                  data-testid={`route-${routeIdx}`}
                >
                  <CardHeader>
                    <div className="flex items-center justify-between">
                      <CardTitle className="text-white">
                        Route {routeIdx + 1}
                        <Badge className="ml-3 bg-purple-600 text-white">
                          Score: {route.score}
                        </Badge>
                      </CardTitle>
                      <div className="flex gap-4 text-sm">
                        <div className="flex items-center text-green-400">
                          <TrendingUp className="w-4 h-4 mr-1" />
                          {route.overall_yield_percent.toFixed(1)}% yield
                        </div>
                        <div className="flex items-center text-yellow-400">
                          <DollarSign className="w-4 h-4 mr-1" />
                          ${route.total_cost_usd.toFixed(2)}
                        </div>
                        <div className="flex items-center text-blue-400">
                          <Clock className="w-4 h-4 mr-1" />
                          {route.total_time_hours.toFixed(1)}h
                        </div>
                      </div>
                    </div>
                  </CardHeader>
                  <CardContent>
                    {/* Starting Materials */}
                    <div className="mb-4">
                      <p className="text-purple-300 font-medium mb-2">Starting Materials:</p>
                      <div className="flex flex-wrap gap-2">
                        {route.starting_materials.map((sm, idx) => (
                          <Badge
                            key={idx}
                            variant="outline"
                            className="bg-blue-500/20 border-blue-400/50 text-blue-200 font-mono text-xs"
                          >
                            {sm.smiles}
                          </Badge>
                        ))}
                      </div>
                    </div>

                    <Separator className="my-4 bg-purple-500/30" />

                    {/* Reaction Steps */}
                    <div className="space-y-4">
                      <p className="text-purple-300 font-medium">Synthesis Steps:</p>
                      {route.steps.map((step, stepIdx) => (
                        <div
                          key={step.id}
                          className="bg-white/5 rounded-lg p-4 border border-purple-500/20"
                        >
                          <div className="flex items-start justify-between mb-3">
                            <div className="flex items-center gap-2">
                              <div className="bg-purple-600 text-white rounded-full w-8 h-8 flex items-center justify-center font-bold">
                                {stepIdx + 1}
                              </div>
                              <div>
                                <p className="text-white font-semibold">
                                  {step.reaction_type}
                                </p>
                                <Badge
                                  className={`${getDifficultyColor(step.difficulty)} text-white text-xs mt-1`}
                                >
                                  {step.difficulty}
                                </Badge>
                              </div>
                            </div>
                            <div className="text-right text-sm">
                              <p className="text-green-400">Yield: {step.estimated_yield_percent}%</p>
                              <p className="text-yellow-400">Cost: ${step.estimated_cost_usd.toFixed(2)}</p>
                            </div>
                          </div>

                          {/* Reaction */}
                          <div className="mb-3">
                            <p className="text-purple-300 text-xs mb-1">Reactants:</p>
                            <div className="flex flex-wrap gap-2 mb-2">
                              {step.reactants.map((r, idx) => (
                                <code key={idx} className="text-xs bg-slate-800/50 px-2 py-1 rounded text-purple-200">
                                  {r.smiles}
                                </code>
                              ))}
                            </div>
                            <p className="text-purple-300 text-xs mb-1">Product:</p>
                            <code className="text-xs bg-slate-800/50 px-2 py-1 rounded text-green-300 block">
                              {step.product.smiles}
                            </code>
                          </div>

                          {/* Conditions */}
                          {step.conditions && (
                            <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs text-purple-200">
                              {step.conditions.temperature_celsius && (
                                <div>
                                  <span className="text-purple-400">Temp:</span> {step.conditions.temperature_celsius}°C
                                </div>
                              )}
                              {step.conditions.solvent && (
                                <div>
                                  <span className="text-purple-400">Solvent:</span> {step.conditions.solvent}
                                </div>
                              )}
                              {step.conditions.catalyst && (
                                <div>
                                  <span className="text-purple-400">Catalyst:</span> {step.conditions.catalyst}
                                </div>
                              )}
                              {step.conditions.time_hours && (
                                <div>
                                  <span className="text-purple-400">Time:</span> {step.conditions.time_hours}h
                                </div>
                              )}
                            </div>
                          )}

                          {step.notes && (
                            <p className="text-xs text-purple-300 mt-2 italic">{step.notes}</p>
                          )}
                        </div>
                      ))}
                    </div>

                    {route.notes && (
                      <Alert className="mt-4 bg-purple-500/10 border-purple-500/30">
                        <AlertDescription className="text-purple-200">
                          {route.notes}
                        </AlertDescription>
                      </Alert>
                    )}
                  </CardContent>
                </Card>
              ))}
            </div>
          </div>
        )}

        {result && result.routes && result.routes.length === 0 && (
          <Alert className="bg-yellow-500/20 border-yellow-500/50">
            <AlertCircle className="h-4 w-4 text-yellow-400" />
            <AlertDescription className="text-yellow-200">
              No synthesis routes found. The molecule may be too complex or require specialized reactions.
            </AlertDescription>
          </Alert>
        )}
      </div>
    </div>
  );
};

export default SynthesisPlannerPage;
