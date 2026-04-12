import React, { useState } from "react";
import axios from "axios";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription } from "@/components/ui/alert";
import {
  Thermometer,
  Loader2,
  AlertCircle,
  Beaker,
  Gauge,
  Droplets,
  Flame,
  Plus,
  X,
} from "lucide-react";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const ConditionPredictorPage = () => {
  const [reactants, setReactants] = useState(["CC(=O)O", "c1ccc(O)cc1"]);
  const [products, setProducts] = useState(["CC(=O)Oc1ccccc1"]);
  const [reactionType, setReactionType] = useState("esterification");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  const addReactant = () => setReactants([...reactants, ""]);
  const addProduct = () => setProducts([...products, ""]);
  const removeReactant = (idx) => setReactants(reactants.filter((_, i) => i !== idx));
  const removeProduct = (idx) => setProducts(products.filter((_, i) => i !== idx));
  const updateReactant = (idx, val) => {
    const copy = [...reactants];
    copy[idx] = val;
    setReactants(copy);
  };
  const updateProduct = (idx, val) => {
    const copy = [...products];
    copy[idx] = val;
    setProducts(copy);
  };

  const predictConditions = async () => {
    const validReactants = reactants.filter((r) => r.trim());
    const validProducts = products.filter((p) => p.trim());

    if (validReactants.length === 0 || validProducts.length === 0) {
      setError("Please provide at least one reactant and one product");
      return;
    }

    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const response = await axios.post(`${API}/conditions/predict`, {
        reactants: validReactants,
        products: validProducts,
        reaction_type: reactionType || null,
      });
      setResult(response.data);
    } catch (e) {
      console.error("Prediction error:", e);
      setError(e.response?.data?.detail || "Failed to predict conditions");
    } finally {
      setLoading(false);
    }
  };

  const presetReactions = [
    {
      name: "Esterification",
      reactants: ["CC(=O)O", "c1ccc(O)cc1"],
      products: ["CC(=O)Oc1ccccc1"],
      type: "esterification",
    },
    {
      name: "Suzuki Coupling",
      reactants: ["c1ccc(Br)cc1", "c1ccc(B(O)O)cc1"],
      products: ["c1ccc(-c2ccccc2)cc1"],
      type: "suzuki_coupling",
    },
    {
      name: "Amide Formation",
      reactants: ["CC(=O)O", "CN"],
      products: ["CC(=O)NC"],
      type: "amide_coupling",
    },
  ];

  return (
    <div className="max-w-5xl mx-auto">
      <div className="flex items-center gap-3 mb-6">
        <Thermometer className="w-8 h-8 text-purple-400" />
        <div>
          <h1 className="text-3xl font-bold text-white">Condition Predictor</h1>
          <p className="text-purple-200/70 text-sm">
            ML-based optimal reaction condition predictions
          </p>
        </div>
      </div>

      {/* Preset Reactions */}
      <div className="mb-6">
        <label className="text-purple-200/60 text-xs mb-2 block">Quick presets:</label>
        <div className="flex flex-wrap gap-2">
          {presetReactions.map((preset) => (
            <Button
              key={preset.name}
              onClick={() => {
                setReactants(preset.reactants);
                setProducts(preset.products);
                setReactionType(preset.type);
              }}
              variant="outline"
              size="sm"
              className="bg-purple-500/10 border-purple-500/30 text-purple-200 text-xs"
            >
              {preset.name}
            </Button>
          ))}
        </div>
      </div>

      {/* Input */}
      <Card className="bg-white/5 backdrop-blur-md border-purple-500/20 mb-6">
        <CardContent className="p-6 space-y-6">
          {/* Reactants */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="text-white font-medium">Reactants (SMILES)</label>
              <Button onClick={addReactant} variant="ghost" size="sm" className="text-purple-300">
                <Plus className="w-4 h-4 mr-1" /> Add
              </Button>
            </div>
            <div className="space-y-2">
              {reactants.map((r, idx) => (
                <div key={idx} className="flex gap-2">
                  <Input
                    value={r}
                    onChange={(e) => updateReactant(idx, e.target.value)}
                    placeholder="Enter SMILES..."
                    className="flex-1 bg-white/10 border-purple-500/30 text-white font-mono text-sm placeholder:text-purple-300/40"
                  />
                  {reactants.length > 1 && (
                    <Button
                      onClick={() => removeReactant(idx)}
                      variant="ghost"
                      size="sm"
                      className="text-red-400 hover:text-red-300"
                    >
                      <X className="w-4 h-4" />
                    </Button>
                  )}
                </div>
              ))}
            </div>
          </div>

          {/* Products */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="text-white font-medium">Products (SMILES)</label>
              <Button onClick={addProduct} variant="ghost" size="sm" className="text-purple-300">
                <Plus className="w-4 h-4 mr-1" /> Add
              </Button>
            </div>
            <div className="space-y-2">
              {products.map((p, idx) => (
                <div key={idx} className="flex gap-2">
                  <Input
                    value={p}
                    onChange={(e) => updateProduct(idx, e.target.value)}
                    placeholder="Enter SMILES..."
                    className="flex-1 bg-white/10 border-purple-500/30 text-white font-mono text-sm placeholder:text-purple-300/40"
                  />
                  {products.length > 1 && (
                    <Button
                      onClick={() => removeProduct(idx)}
                      variant="ghost"
                      size="sm"
                      className="text-red-400 hover:text-red-300"
                    >
                      <X className="w-4 h-4" />
                    </Button>
                  )}
                </div>
              ))}
            </div>
          </div>

          {/* Reaction Type */}
          <div>
            <label className="text-white font-medium mb-2 block">Reaction Type (optional)</label>
            <Input
              value={reactionType}
              onChange={(e) => setReactionType(e.target.value)}
              placeholder="e.g., esterification, suzuki_coupling"
              className="bg-white/10 border-purple-500/30 text-white placeholder:text-purple-300/40"
            />
          </div>

          <Button
            onClick={predictConditions}
            disabled={loading}
            className="w-full bg-gradient-to-r from-teal-600 to-cyan-600 text-white"
          >
            {loading ? (
              <><Loader2 className="w-4 h-4 animate-spin mr-2" /> Predicting...</>
            ) : (
              <><Thermometer className="w-4 h-4 mr-2" /> Predict Optimal Conditions</>
            )}
          </Button>
        </CardContent>
      </Card>

      {/* Error */}
      {error && (
        <Alert className="mb-6 bg-red-500/20 border-red-500/50">
          <AlertCircle className="h-4 w-4 text-red-400" />
          <AlertDescription className="text-red-200">{error}</AlertDescription>
        </Alert>
      )}

      {/* Results */}
      {result && result.conditions && (
        <Card className="bg-white/5 backdrop-blur-md border-purple-500/20">
          <CardHeader>
            <CardTitle className="text-white">Predicted Conditions</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {Object.entries(result.conditions).map(([key, value]) => {
                const icons = {
                  temperature: Flame,
                  solvent: Droplets,
                  catalyst: Beaker,
                  pressure: Gauge,
                };
                const matchedIcon = Object.entries(icons).find(([k]) =>
                  key.toLowerCase().includes(k)
                );
                const Icon = matchedIcon ? matchedIcon[1] : Thermometer;

                return (
                  <div key={key} className="bg-white/5 rounded-lg p-4 border border-purple-500/20">
                    <div className="flex items-center gap-2 mb-2">
                      <Icon className="w-4 h-4 text-teal-400" />
                      <span className="text-purple-300/70 text-xs capitalize">
                        {key.replace(/_/g, " ")}
                      </span>
                    </div>
                    <p className="text-white font-semibold">
                      {typeof value === "object" ? JSON.stringify(value) : String(value)}
                    </p>
                  </div>
                );
              })}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
};

export default ConditionPredictorPage;
