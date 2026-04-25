import React, { useState } from "react";
import { Link, useLocation } from "react-router-dom";
import useSynthesisStore from "../store/synthesisStore";
import {
  Beaker,
  FlaskConical,
  History,
  MessageSquare,
  Search,
  Scale,
  Thermometer,
  Wrench,
  ChevronLeft,
  ChevronRight,
  LayoutDashboard,
  GitBranch,
  Zap,
  Target,
} from "lucide-react";

const navItems = [
  { path: "/", label: "Dashboard", icon: LayoutDashboard },
  { path: "/planner", label: "Synthesis Planner", icon: Beaker },
  { path: "/retrosynthesis", label: "Retrosynthesis", icon: GitBranch },
  { path: "/analyzer", label: "Molecule Analyzer", icon: Search },
  { path: "/copilot", label: "AI Copilot", icon: MessageSquare },
  { path: "/optimizer", label: "Route Optimizer", icon: Zap },
  { path: "/convergence", label: "Convergence Loop", icon: Target },
  { path: "/yield", label: "Yield Optimizer", icon: FlaskConical },
  { path: "/scale-up", label: "Scale-Up & Cost", icon: Scale },
  { path: "/conditions", label: "Condition Predictor", icon: Thermometer },
  { path: "/equipment", label: "Equipment", icon: Wrench },
  { path: "/history", label: "History", icon: History },
];

const Layout = ({ children }) => {
  const location = useLocation();
  const [collapsed, setCollapsed] = useState(false);
  const { targetSmiles, plannedRoutes, planningHistory, clearSession } = useSynthesisStore();
  const hasSession = plannedRoutes.length > 0;

  return (
    <div className="flex min-h-screen bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900">
      {/* Sidebar */}
      <aside
        className={`${
          collapsed ? "w-16" : "w-64"
        } transition-all duration-300 bg-black/30 backdrop-blur-xl border-r border-purple-500/20 flex flex-col fixed h-full z-50`}
      >
        {/* Logo */}
        <div className="p-4 border-b border-purple-500/20 flex items-center gap-3">
          <FlaskConical className="w-8 h-8 text-purple-400 flex-shrink-0" />
          {!collapsed && (
            <div>
              <h1 className="text-lg font-bold text-white leading-tight">
                SynthAI
              </h1>
              <p className="text-[10px] text-purple-300">Route Planner</p>
            </div>
          )}
        </div>

        {/* Nav Items */}
        <nav className="flex-1 py-4 space-y-1 px-2 overflow-y-auto">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = location.pathname === item.path;
            return (
              <Link
                key={item.path}
                to={item.path}
                className={`flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all duration-200 group ${
                  isActive
                    ? "bg-purple-600/30 text-white border border-purple-500/40"
                    : "text-purple-200/70 hover:bg-purple-600/15 hover:text-white"
                }`}
                title={collapsed ? item.label : undefined}
              >
                <Icon
                  className={`w-5 h-5 flex-shrink-0 ${
                    isActive
                      ? "text-purple-300"
                      : "text-purple-400/60 group-hover:text-purple-300"
                  }`}
                />
                {!collapsed && (
                  <span className="text-sm font-medium truncate">
                    {item.label}
                  </span>
                )}
              </Link>
            );
          })}
        </nav>

        {/* Session status indicator */}
        {!collapsed && (hasSession || planningHistory.length > 0) && (
          <div style={{
            margin: '0 8px 4px', padding: '8px 10px',
            background: hasSession ? 'rgba(139,92,246,0.15)' : 'rgba(255,255,255,0.04)',
            border: `1px solid ${hasSession ? 'rgba(139,92,246,0.4)' : 'rgba(255,255,255,0.08)'}`,
            borderRadius: 8, fontSize: 11,
          }}>
            {hasSession ? (
              <div style={{ display: 'flex', alignItems: 'flex-start', gap: 6 }}>
                <span style={{ color: '#a78bfa', flexShrink: 0, marginTop: 1 }}>📋</span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ color: '#e9d5ff', fontWeight: 600, marginBottom: 2 }}>Active session</div>
                  <div style={{ color: '#7c3aed', fontFamily: 'monospace', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {targetSmiles.slice(0, 22)}{targetSmiles.length > 22 ? '…' : ''}
                  </div>
                </div>
                <button
                  onClick={clearSession}
                  title="Clear session"
                  style={{ background: 'none', border: 'none', color: '#f87171', cursor: 'pointer', fontSize: 14, lineHeight: 1, padding: 0, flexShrink: 0 }}
                >
                  ×
                </button>
              </div>
            ) : (
              <div style={{ color: '#6d28d9', textAlign: 'center' }}>
                🕐 {planningHistory.length} recent session{planningHistory.length > 1 ? 's' : ''}
              </div>
            )}
          </div>
        )}

        {/* Collapse Toggle */}
        <button
          onClick={() => setCollapsed(!collapsed)}
          className="p-3 border-t border-purple-500/20 text-purple-300 hover:text-white hover:bg-purple-600/20 transition-colors flex items-center justify-center"
        >
          {collapsed ? (
            <ChevronRight className="w-5 h-5" />
          ) : (
            <ChevronLeft className="w-5 h-5" />
          )}
        </button>
      </aside>

      {/* Main Content */}
      <main
        className={`flex-1 transition-all duration-300 ${
          collapsed ? "ml-16" : "ml-64"
        }`}
      >
        <div className="p-6 min-h-screen">{children}</div>
      </main>
    </div>
  );
};

export default Layout;
