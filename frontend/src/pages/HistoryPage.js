import React, { useState, useEffect } from "react";
import axios from "axios";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  History,
  Search,
  Beaker,
  TrendingUp,
  DollarSign,
  Clock,
  ChevronDown,
  ChevronUp,
  Loader2,
  AlertCircle,
} from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const HistoryPage = () => {
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [searchTerm, setSearchTerm] = useState("");
  const [expandedItem, setExpandedItem] = useState(null);
  const [limit, setLimit] = useState(20);

  useEffect(() => {
    fetchHistory();
  }, [limit]);

  const fetchHistory = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await axios.get(`${API}/synthesis/history?limit=${limit}`);
      setHistory(response.data.history || []);
    } catch (e) {
      console.error("History fetch error:", e);
      setError("Failed to fetch synthesis history");
    } finally {
      setLoading(false);
    }
  };

  const filteredHistory = history.filter((item) =>
    searchTerm
      ? item.target_smiles?.toLowerCase().includes(searchTerm.toLowerCase()) ||
        item.optimization_goal?.toLowerCase().includes(searchTerm.toLowerCase())
      : true
  );

  return (
    <div className="max-w-6xl mx-auto">
      <div className="flex items-center gap-3 mb-6">
        <History className="w-8 h-8 text-purple-400" />
        <div>
          <h1 className="text-3xl font-bold text-white">Synthesis History</h1>
          <p className="text-purple-200/70 text-sm">Browse past synthesis planning results</p>
        </div>
      </div>

      {/* Search & Filter */}
      <Card className="bg-white/5 backdrop-blur-md border-purple-500/20 mb-6">
        <CardContent className="p-4 flex gap-4 items-center">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-purple-300/50" />
            <Input
              placeholder="Search by SMILES or optimization goal..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="pl-10 bg-white/10 border-purple-500/30 text-white placeholder:text-purple-300/40"
            />
          </div>
          <select
            value={limit}
            onChange={(e) => setLimit(parseInt(e.target.value))}
            className="bg-white/10 border border-purple-500/30 rounded-md px-3 py-2 text-white text-sm"
          >
            <option value={10} className="bg-slate-800">10 items</option>
            <option value={20} className="bg-slate-800">20 items</option>
            <option value={50} className="bg-slate-800">50 items</option>
          </select>
          <Button onClick={fetchHistory} variant="outline" className="bg-purple-500/20 border-purple-400/50 text-purple-200">
            Refresh
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

      {/* Loading */}
      {loading && (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="w-8 h-8 animate-spin text-purple-400" />
          <span className="ml-3 text-purple-200">Loading history...</span>
        </div>
      )}

      {/* Empty State */}
      {!loading && filteredHistory.length === 0 && (
        <Card className="bg-white/5 backdrop-blur-md border-purple-500/20">
          <CardContent className="p-12 text-center">
            <History className="w-12 h-12 text-purple-400/40 mx-auto mb-4" />
            <h3 className="text-white font-semibold mb-2">
              {searchTerm ? "No matching results" : "No history yet"}
            </h3>
            <p className="text-purple-200/60 text-sm">
              {searchTerm
                ? "Try a different search term"
                : "Run your first synthesis plan to see it here"}
            </p>
          </CardContent>
        </Card>
      )}

      {/* History List */}
      <div className="space-y-3">
        {filteredHistory.map((item, idx) => (
          <Card key={idx} className="bg-white/5 backdrop-blur-md border-purple-500/20 hover:bg-white/8 transition-colors">
            <CardContent className="p-0">
              {/* Summary Row */}
              <button
                onClick={() => setExpandedItem(expandedItem === idx ? null : idx)}
                className="w-full p-4 flex items-center justify-between text-left"
              >
                <div className="flex items-center gap-4 flex-1 min-w-0">
                  <Beaker className="w-5 h-5 text-purple-400 flex-shrink-0" />
                  <div className="min-w-0 flex-1">
                    <p className="text-white font-mono text-sm truncate">
                      {item.target_smiles}
                    </p>
                    <div className="flex items-center gap-3 mt-1">
                      <Badge variant="outline" className="border-purple-500/40 text-purple-300 text-xs">
                        {item.optimization_goal || "balanced"}
                      </Badge>
                      <span className="text-purple-300/50 text-xs">
                        {item.routes?.length || 0} routes
                      </span>
                      {item.computation_time_seconds && (
                        <span className="text-purple-300/50 text-xs">
                          {item.computation_time_seconds}s
                        </span>
                      )}
                    </div>
                  </div>
                </div>
                {expandedItem === idx ? (
                  <ChevronUp className="w-5 h-5 text-purple-300" />
                ) : (
                  <ChevronDown className="w-5 h-5 text-purple-300" />
                )}
              </button>

              {/* Expanded Details */}
              {expandedItem === idx && item.routes && (
                <div className="px-4 pb-4 border-t border-purple-500/20 pt-4">
                  <div className="space-y-3">
                    {item.routes.map((route, rIdx) => (
                      <div key={rIdx} className="bg-white/5 rounded-lg p-3">
                        <div className="flex items-center justify-between mb-2">
                          <span className="text-white font-semibold text-sm">
                            Route {rIdx + 1}
                          </span>
                          <div className="flex gap-3 text-xs">
                            <span className="text-green-400 flex items-center gap-1">
                              <TrendingUp className="w-3 h-3" />
                              {route.overall_yield_percent?.toFixed(1)}%
                            </span>
                            <span className="text-yellow-400 flex items-center gap-1">
                              <DollarSign className="w-3 h-3" />
                              ${route.total_cost_usd?.toFixed(2)}
                            </span>
                            <span className="text-blue-400 flex items-center gap-1">
                              <Clock className="w-3 h-3" />
                              {route.total_time_hours?.toFixed(1)}h
                            </span>
                          </div>
                        </div>
                        <div className="text-purple-300/60 text-xs">
                          {route.steps?.length || 0} steps •
                          Score: {route.score}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
};

export default HistoryPage;
