import React from "react";
import "@/App.css";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import Layout from "@/components/Layout";
import DashboardPage from "@/pages/DashboardPage";
import SynthesisPlannerPage from "@/pages/SynthesisPlannerPage";
import HistoryPage from "@/pages/HistoryPage";
import CopilotPage from "@/pages/CopilotPage";
import MoleculeAnalyzerPage from "@/pages/MoleculeAnalyzerPage";
import RetrosynthesisPage from "@/pages/RetrosynthesisPage";
import ScaleUpPage from "@/pages/ScaleUpPage";
import ConditionPredictorPage from "@/pages/ConditionPredictorPage";
import EquipmentPage from "@/pages/EquipmentPage";
import RouteOptimizerPage from "@/pages/RouteOptimizerPage";
import ConvergenceLoopPage from "@/pages/ConvergenceLoopPage";
import YieldOptimizerPage from "@/pages/YieldOptimizerPage";

function App() {
  return (
    <BrowserRouter>
      <Layout>
        <Routes>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/planner" element={<SynthesisPlannerPage />} />
          <Route path="/retrosynthesis" element={<RetrosynthesisPage />} />
          <Route path="/analyzer" element={<MoleculeAnalyzerPage />} />
          <Route path="/copilot" element={<CopilotPage />} />
          <Route path="/scale-up" element={<ScaleUpPage />} />
          <Route path="/conditions" element={<ConditionPredictorPage />} />
          <Route path="/equipment" element={<EquipmentPage />} />
          <Route path="/optimizer" element={<RouteOptimizerPage />} />
          <Route path="/convergence" element={<ConvergenceLoopPage />} />
          <Route path="/yield" element={<YieldOptimizerPage />} />
          <Route path="/history" element={<HistoryPage />} />
        </Routes>
      </Layout>
    </BrowserRouter>
  );
}

export default App;
