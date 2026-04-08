import React, { useState } from "react";
import axios from "axios";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Separator } from "@/components/ui/separator";
import {
  Search,
  Loader2,
  AlertCircle,
  CheckCircle2,
  Atom,
  Weight,
  Droplets,
  Ruler,
  Shield,
  Fingerprint,
} from "lucide-react";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const exampleMolecules = [
  { name: "Aspirin", smiles: "CC(=O)Oc1ccccc1C(=O)O" },
  { name: "Caffeine", smiles: "CN1C=NC2=C1C(=O)N(C(=O)N2C)C" },
  { name: "Ibuprofen", smiles: "CC(C)Cc1ccc(cc1)C(C)C(=O)O" },
  { name: "Paracetamol", smiles: "CC(=O)Nc1ccc(O)cc1" },
  { name: "Benzene", smiles: "c1ccccc1" },
  { name: "Ethanol", smiles: "CCO" },
  { name: "Glucose", smiles: "OC[C@H]1OC(O)[C@H](O)[C@@H](O)[C@@H]1O" },
  { name: "Cholesterol", smiles: "CC(C)CCCC(C)C1CCC2C1(CCC3C2CC=C4C3(CCC(C4)O)C)C" },
];

const MoleculeAnalyzerPage = () => {
  const [smiles, setSmiles] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  const analyzeMolecule = async (smilesInput) => {
    const target = smilesInput || smiles;
    if (!target.trim()) {
      setError("Please enter a SMILES string");
      return;
    }

    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const response = await axios.post(`${API}/molecule/analyze`, {
        smiles: target,
      });
      setResult(response.data);
    } catch (e) {
      console.error("Analysis error:", e);
      setError(
        e.response?.data?.detail || "Failed to analyze molecule. Check SMILES."
      );
    } finally {
      setLoading(false);
    }
  };

  const PropertyCard = ({ icon: Icon, label, value, unit, color }) => (
    <div className="bg-white/5 rounded-lg p-4 border border-purple-500/20">
      <div className="flex items-center gap-2 mb-2">
        <Icon className={`w-4 h-4 ${color}`} />
        <span className="text-purple-300/70 text-xs">{label}</span>
      </div>
      <p className="text-white text-xl font-bold">
        {typeof value === "number" ? value.toFixed(2) : value}
        {unit && <span className="text-purple-300/60 text-sm ml-1">{unit}</span>}
      </p>
    </div>
  );

  return (
    <div className="max-w-6xl mx-auto">
      {/* Header */}
      <div className="flex items-center gap-3 mb-6">
        <Search className="w-8 h-8 text-purple-400" />
        <div>
          <h1 className="text-3xl font-bold text-white">Molecule Analyzer</h1>
          <p className="text-purple-200/70 text-sm">
            Detailed molecular property analysis using RDKit
          </p>
        </div>
      </div>

      {/* Input */}
      <Card className="bg-white/5 backdrop-blur-md border-purple-500/20 mb-6">
        <CardContent className="p-6 space-y-4">
          <div>
            <label className="text-white font-medium mb-2 block">SMILES String</label>
            <div className="flex gap-2">
              <Input
                placeholder="e.g., CC(=O)Oc1ccccc1C(=O)O"
                value={smiles}
                onChange={(e) => setSmiles(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && analyzeMolecule()}
                className="flex-1 bg-white/10 border-purple-500/30 text-white placeholder:text-purple-300/40"
              />
              <Button
                onClick={() => analyzeMolecule()}
                disabled={loading}
                className="bg-gradient-to-r from-purple-600 to-pink-600 text-white px-8"
              >
                {loading ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  "Analyze"
                )}
              </Button>
            </div>
          </div>

          <div>
            <label className="text-purple-200/60 text-sm mb-2 block">
              Quick examples:
            </label>
            <div className="flex flex-wrap gap-2">
              {exampleMolecules.map((mol) => (
                <Button
                  key={mol.name}
                  onClick={() => {
                    setSmiles(mol.smiles);
                    analyzeMolecule(mol.smiles);
                  }}
                  variant="outline"
                  size="sm"
                  className="bg-purple-500/10 border-purple-500/30 text-purple-200 text-xs hover:bg-purple-500/20"
                >
                  {mol.name}
                </Button>
              ))}
            </div>
          </div>
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
      {result && result.valid && (
        <div className="space-y-6">
          {/* Validation Status */}
          <Alert className="bg-green-500/20 border-green-500/50">
            <CheckCircle2 className="h-4 w-4 text-green-400" />
            <AlertDescription className="text-green-200">
              Valid molecule — {result.name || result.molecular_formula || "Unknown"}
            </AlertDescription>
          </Alert>

          {/* Key Properties Grid */}
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
            <PropertyCard
              icon={Weight}
              label="Molecular Weight"
              value={result.molecular_weight}
              unit="g/mol"
              color="text-blue-400"
            />
            <PropertyCard
              icon={Atom}
              label="Formula"
              value={result.molecular_formula || "N/A"}
              color="text-green-400"
            />
            <PropertyCard
              icon={Droplets}
              label="LogP"
              value={result.logp}
              color="text-cyan-400"
            />
            <PropertyCard
              icon={Ruler}
              label="TPSA"
              value={result.tpsa}
              unit="\u00C5\u00B2"
              color="text-orange-400"
            />
            <PropertyCard
              icon={Shield}
              label="H-Bond Donors"
              value={result.h_donors}
              color="text-pink-400"
            />
            <PropertyCard
              icon={Fingerprint}
              label="H-Bond Acceptors"
              value={result.h_acceptors}
              color="text-violet-400"
            />
          </div>

          {/* Detailed Properties */}
          <Card className="bg-white/5 backdrop-blur-md border-purple-500/20">
            <CardHeader>
              <CardTitle className="text-white text-lg">Detailed Properties</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {/* Lipinski's Rule */}
                <div className="bg-white/5 rounded-lg p-4 border border-purple-500/20">
                  <h3 className="text-white font-semibold mb-3 text-sm">
                    Lipinski's Rule of Five
                  </h3>
                  <div className="space-y-2">
                    {[
                      { label: "MW ≤ 500", pass: (result.molecular_weight || 0) <= 500 },
                      { label: "LogP ≤ 5", pass: (result.logp || 0) <= 5 },
                      { label: "H-Donors ≤ 5", pass: (result.h_donors || 0) <= 5 },
                      { label: "H-Acceptors ≤ 10", pass: (result.h_acceptors || 0) <= 10 },
                    ].map((rule, i) => (
                      <div key={i} className="flex items-center justify-between">
                        <span className="text-purple-200/70 text-sm">{rule.label}</span>
                        <Badge
                          className={`${
                            rule.pass
                              ? "bg-green-500/20 text-green-300 border-green-500/30"
                              : "bg-red-500/20 text-red-300 border-red-500/30"
                          } text-xs`}
                        >
                          {rule.pass ? "PASS" : "FAIL"}
                        </Badge>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Structural Info */}
                <div className="bg-white/5 rounded-lg p-4 border border-purple-500/20">
                  <h3 className="text-white font-semibold mb-3 text-sm">
                    Structural Information
                  </h3>
                  <div className="space-y-2">
                    {[
                      { label: "Rotatable Bonds", value: result.rotatable_bonds },
                      { label: "Total Atoms", value: result.num_atoms },
                      { label: "Total Bonds", value: result.num_bonds },
                      { label: "Lipinski Violations", value: result.lipinski_violations },
                    ].map((item, i) => (
                      <div key={i} className="flex items-center justify-between">
                        <span className="text-purple-200/70 text-sm">{item.label}</span>
                        <span className="text-white font-mono text-sm">
                          {item.value ?? "N/A"}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              {/* SMILES canonical */}
              {result.canonical_smiles && (
                <div className="mt-4 bg-white/5 rounded-lg p-4 border border-purple-500/20">
                  <h3 className="text-white font-semibold mb-2 text-sm">
                    Canonical SMILES
                  </h3>
                  <code className="text-purple-200 font-mono text-sm bg-slate-800/50 px-3 py-2 rounded block">
                    {result.canonical_smiles}
                  </code>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
};

export default MoleculeAnalyzerPage;
