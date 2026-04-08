import React, { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import axios from "axios";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Beaker,
  GitBranch,
  History,
  MessageSquare,
  Search,
  Scale,
  Thermometer,
  Wrench,
  ArrowRight,
  Activity,
  Database,
  Cpu,
  FlaskConical,
} from "lucide-react";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const DashboardPage = () => {
  const [stats, setStats] = useState(null);
  const [recentHistory, setRecentHistory] = useState([]);
  const [templateStats, setTemplateStats] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [historyRes, templatesRes] = await Promise.allSettled([
          axios.get(`${API}/synthesis/history?limit=5`),
          axios.get(`${API}/templates/stats`),
        ]);

        if (historyRes.status === "fulfilled") {
          setRecentHistory(historyRes.value.data.history || []);
        }
        if (templatesRes.status === "fulfilled") {
          setTemplateStats(templatesRes.value.data.statistics || null);
        }
      } catch (e) {
        console.error("Dashboard fetch error:", e);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, []);

  const features = [
    {
      title: "Synthesis Planner",
      desc: "AI-powered route planning with Claude",
      icon: Beaker,
      link: "/planner",
      color: "from-purple-500 to-pink-500",
    },
    {
      title: "Retrosynthesis",
      desc: "Tree-based retrosynthetic analysis",
      icon: GitBranch,
      link: "/retrosynthesis",
      color: "from-blue-500 to-cyan-500",
    },
    {
      title: "Molecule Analyzer",
      desc: "Detailed molecular properties",
      icon: Search,
      link: "/analyzer",
      color: "from-green-500 to-emerald-500",
    },
    {
      title: "AI Copilot",
      desc: "Natural language optimization",
      icon: MessageSquare,
      link: "/copilot",
      color: "from-orange-500 to-amber-500",
    },
    {
      title: "Scale-Up & Cost",
      desc: "Industrial optimization & cost modeling",
      icon: Scale,
      link: "/scale-up",
      color: "from-red-500 to-rose-500",
    },
    {
      title: "Condition Predictor",
      desc: "ML-based reaction conditions",
      icon: Thermometer,
      link: "/conditions",
      color: "from-teal-500 to-cyan-500",
    },
    {
      title: "Equipment",
      desc: "Lab setup recommendations",
      icon: Wrench,
      link: "/equipment",
      color: "from-indigo-500 to-violet-500",
    },
    {
      title: "History",
      desc: "Browse past synthesis plans",
      icon: History,
      link: "/history",
      color: "from-slate-500 to-gray-500",
    },
  ];

  return (
    <div className="max-w-7xl mx-auto">
      {/* Header */}
      <div className="mb-8">
        <div className="flex items-center gap-3 mb-2">
          <FlaskConical className="w-10 h-10 text-purple-400" />
          <div>
            <h1 className="text-3xl font-bold text-white">Dashboard</h1>
            <p className="text-purple-200/70 text-sm">
              AI-Powered Chemical Synthesis Planning Platform
            </p>
          </div>
        </div>
      </div>

      {/* Quick Stats */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
        <Card className="bg-white/5 backdrop-blur-md border-purple-500/20">
          <CardContent className="p-4 flex items-center gap-3">
            <div className="p-2 rounded-lg bg-purple-500/20">
              <Activity className="w-5 h-5 text-purple-400" />
            </div>
            <div>
              <p className="text-xs text-purple-300">Recent Plans</p>
              <p className="text-2xl font-bold text-white">
                {recentHistory.length}
              </p>
            </div>
          </CardContent>
        </Card>
        <Card className="bg-white/5 backdrop-blur-md border-purple-500/20">
          <CardContent className="p-4 flex items-center gap-3">
            <div className="p-2 rounded-lg bg-blue-500/20">
              <Database className="w-5 h-5 text-blue-400" />
            </div>
            <div>
              <p className="text-xs text-purple-300">Template Types</p>
              <p className="text-2xl font-bold text-white">
                {templateStats?.total_types || 8}
              </p>
            </div>
          </CardContent>
        </Card>
        <Card className="bg-white/5 backdrop-blur-md border-purple-500/20">
          <CardContent className="p-4 flex items-center gap-3">
            <div className="p-2 rounded-lg bg-green-500/20">
              <Cpu className="w-5 h-5 text-green-400" />
            </div>
            <div>
              <p className="text-xs text-purple-300">ML Models</p>
              <p className="text-2xl font-bold text-white">3</p>
            </div>
          </CardContent>
        </Card>
        <Card className="bg-white/5 backdrop-blur-md border-purple-500/20">
          <CardContent className="p-4 flex items-center gap-3">
            <div className="p-2 rounded-lg bg-orange-500/20">
              <FlaskConical className="w-5 h-5 text-orange-400" />
            </div>
            <div>
              <p className="text-xs text-purple-300">API Version</p>
              <p className="text-2xl font-bold text-white">1.0</p>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Feature Grid */}
      <h2 className="text-xl font-semibold text-white mb-4">Tools & Features</h2>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        {features.map((feature) => {
          const Icon = feature.icon;
          return (
            <Link key={feature.link} to={feature.link}>
              <Card className="bg-white/5 backdrop-blur-md border-purple-500/20 hover:bg-white/10 hover:border-purple-500/40 transition-all duration-300 cursor-pointer group h-full">
                <CardContent className="p-5">
                  <div
                    className={`w-10 h-10 rounded-lg bg-gradient-to-br ${feature.color} flex items-center justify-center mb-3 group-hover:scale-110 transition-transform`}
                  >
                    <Icon className="w-5 h-5 text-white" />
                  </div>
                  <h3 className="text-white font-semibold mb-1">
                    {feature.title}
                  </h3>
                  <p className="text-purple-200/60 text-xs mb-3">
                    {feature.desc}
                  </p>
                  <div className="flex items-center text-purple-300 text-xs group-hover:text-purple-200 transition-colors">
                    Open <ArrowRight className="w-3 h-3 ml-1" />
                  </div>
                </CardContent>
              </Card>
            </Link>
          );
        })}
      </div>

      {/* Recent History */}
      {recentHistory.length > 0 && (
        <div>
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-xl font-semibold text-white">
              Recent Synthesis Plans
            </h2>
            <Link to="/history">
              <Button
                variant="ghost"
                size="sm"
                className="text-purple-300 hover:text-white"
              >
                View All <ArrowRight className="w-4 h-4 ml-1" />
              </Button>
            </Link>
          </div>
          <div className="space-y-2">
            {recentHistory.map((item, idx) => (
              <Card
                key={idx}
                className="bg-white/5 backdrop-blur-md border-purple-500/20"
              >
                <CardContent className="p-4 flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <Beaker className="w-5 h-5 text-purple-400" />
                    <div>
                      <p className="text-white font-mono text-sm">
                        {item.target_smiles}
                      </p>
                      <p className="text-purple-300/60 text-xs">
                        {item.routes?.length || 0} routes found
                      </p>
                    </div>
                  </div>
                  <Badge
                    variant="outline"
                    className="border-purple-500/40 text-purple-300"
                  >
                    {item.optimization_goal || "balanced"}
                  </Badge>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

export default DashboardPage;
