import React, { useState } from "react";
import axios from "axios";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription } from "@/components/ui/alert";
import {
  Wrench,
  Loader2,
  AlertCircle,
  Star,
  ChevronDown,
  ChevronUp,
  Beaker,
  Flame,
  Gauge,
  Package,
} from "lucide-react";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const EquipmentPage = () => {
  const [reactionType, setReactionType] = useState("esterification");
  const [scaleMg, setScaleMg] = useState(100);
  const [temperatureC, setTemperatureC] = useState(80);
  const [pressureAtm, setPressureAtm] = useState(1);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [expandedReactor, setExpandedReactor] = useState(0);

  const presets = [
    { name: "Small Lab", type: "esterification", scale: 100, temp: 80, press: 1 },
    { name: "Hydrogenation", type: "hydrogenation", scale: 500, temp: 25, press: 50 },
    { name: "High Temp", type: "pyrolysis", scale: 1000, temp: 500, press: 1 },
    { name: "Photochemistry", type: "photochemistry", scale: 50, temp: 25, press: 1 },
  ];

  const recommend = async () => {
    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const response = await axios.post(`${API}/equipment/recommend`, {
        reaction_type: reactionType,
        scale_mg: scaleMg,
        temperature_c: temperatureC,
        pressure_atm: pressureAtm,
      });
      setResult(response.data);
    } catch (e) {
      console.error("Equipment error:", e);
      setError(e.response?.data?.detail || "Failed to get recommendations");
    } finally {
      setLoading(false);
    }
  };

  const getScoreStars = (score) => {
    const stars = Math.round((score || 0) * 5);
    return Array.from({ length: 5 }, (_, i) => (
      <Star
        key={i}
        className={`w-3 h-3 ${
          i < stars ? "text-yellow-400 fill-yellow-400" : "text-gray-600"
        }`}
      />
    ));
  };

  return (
    <div className="max-w-6xl mx-auto">
      <div className="flex items-center gap-3 mb-6">
        <Wrench className="w-8 h-8 text-purple-400" />
        <div>
          <h1 className="text-3xl font-bold text-white">Equipment Recommender</h1>
          <p className="text-purple-200/70 text-sm">
            Lab equipment and reactor recommendations
          </p>
        </div>
      </div>

      {/* Presets */}
      <div className="mb-6">
        <label className="text-purple-200/60 text-xs mb-2 block">Quick presets:</label>
        <div className="flex flex-wrap gap-2">
          {presets.map((p) => (
            <Button
              key={p.name}
              onClick={() => {
                setReactionType(p.type);
                setScaleMg(p.scale);
                setTemperatureC(p.temp);
                setPressureAtm(p.press);
              }}
              variant="outline"
              size="sm"
              className="bg-purple-500/10 border-purple-500/30 text-purple-200 text-xs"
            >
              {p.name}
            </Button>
          ))}
        </div>
      </div>

      {/* Input */}
      <Card className="bg-white/5 backdrop-blur-md border-purple-500/20 mb-6">
        <CardContent className="p-6 space-y-4">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div>
              <label className="text-purple-200/70 text-xs mb-1 block">Reaction Type</label>
              <Input
                value={reactionType}
                onChange={(e) => setReactionType(e.target.value)}
                placeholder="e.g., esterification"
                className="bg-white/10 border-purple-500/30 text-white text-sm"
              />
            </div>
            <div>
              <label className="text-purple-200/70 text-xs mb-1 block flex items-center gap-1">
                <Beaker className="w-3 h-3" /> Scale (mg)
              </label>
              <Input
                type="number"
                value={scaleMg}
                onChange={(e) => setScaleMg(parseFloat(e.target.value))}
                className="bg-white/10 border-purple-500/30 text-white text-sm"
              />
            </div>
            <div>
              <label className="text-purple-200/70 text-xs mb-1 block flex items-center gap-1">
                <Flame className="w-3 h-3" /> Temperature (°C)
              </label>
              <Input
                type="number"
                value={temperatureC}
                onChange={(e) => setTemperatureC(parseFloat(e.target.value))}
                className="bg-white/10 border-purple-500/30 text-white text-sm"
              />
            </div>
            <div>
              <label className="text-purple-200/70 text-xs mb-1 block flex items-center gap-1">
                <Gauge className="w-3 h-3" /> Pressure (atm)
              </label>
              <Input
                type="number"
                value={pressureAtm}
                onChange={(e) => setPressureAtm(parseFloat(e.target.value))}
                className="bg-white/10 border-purple-500/30 text-white text-sm"
              />
            </div>
          </div>

          <Button
            onClick={recommend}
            disabled={loading}
            className="w-full bg-gradient-to-r from-indigo-600 to-violet-600 text-white"
          >
            {loading ? (
              <><Loader2 className="w-4 h-4 animate-spin mr-2" /> Recommending...</>
            ) : (
              <><Wrench className="w-4 h-4 mr-2" /> Get Recommendations</>
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
      {result && (
        <div className="space-y-6">
          {/* Reactor Recommendations */}
          {result.reactor_recommendations && result.reactor_recommendations.length > 0 && (
            <div>
              <h2 className="text-xl font-semibold text-white mb-4">Reactor Recommendations</h2>
              <div className="space-y-3">
                {result.reactor_recommendations.map((rec, idx) => (
                  <Card key={idx} className="bg-white/5 backdrop-blur-md border-purple-500/20">
                    <CardContent className="p-0">
                      <button
                        onClick={() => setExpandedReactor(expandedReactor === idx ? null : idx)}
                        className="w-full p-4 flex items-center justify-between text-left"
                      >
                        <div className="flex items-center gap-3">
                          <div className="w-8 h-8 rounded-full bg-indigo-600/30 flex items-center justify-center">
                            <Package className="w-4 h-4 text-indigo-300" />
                          </div>
                          <div>
                            <span className="text-white font-semibold">
                              {rec.name || rec.reactor || rec.reactor_type || `Reactor ${idx + 1}`}
                            </span>
                            <div className="flex gap-1 mt-1">
                              {getScoreStars(rec.score > 1 ? rec.score / 100 : rec.score)}
                            </div>
                          </div>
                        </div>
                        <div className="flex items-center gap-3">
                          {rec.score && (
                            <Badge className="bg-indigo-600/30 text-indigo-200">
                              Score: {rec.score > 1 ? rec.score : (rec.score * 100).toFixed(0) + "%"}
                            </Badge>
                          )}
                          {expandedReactor === idx ? (
                            <ChevronUp className="w-5 h-5 text-purple-300" />
                          ) : (
                            <ChevronDown className="w-5 h-5 text-purple-300" />
                          )}
                        </div>
                      </button>

                      {expandedReactor === idx && (
                        <div className="px-4 pb-4 border-t border-purple-500/20 pt-4">
                          {rec.reasoning && (
                            <p className="text-purple-200/70 text-sm mb-3">{rec.reasoning}</p>
                          )}
                          <pre className="text-purple-200 text-xs font-mono bg-slate-800/50 p-3 rounded-lg overflow-auto">
                            {JSON.stringify(rec, null, 2)}
                          </pre>
                        </div>
                      )}
                    </CardContent>
                  </Card>
                ))}
              </div>
            </div>
          )}

          {/* Complete Setup */}
          {result.complete_setup && (
            <Card className="bg-white/5 backdrop-blur-md border-purple-500/20">
              <CardHeader>
                <CardTitle className="text-white">Complete Lab Setup</CardTitle>
              </CardHeader>
              <CardContent>
                <pre className="text-purple-200 text-xs font-mono bg-slate-800/50 p-4 rounded-lg overflow-auto max-h-96">
                  {JSON.stringify(result.complete_setup, null, 2)}
                </pre>
              </CardContent>
            </Card>
          )}
        </div>
      )}
    </div>
  );
};

export default EquipmentPage;
