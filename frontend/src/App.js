import { useState } from "react";
import "@/App.css";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import SynthesisPlannerPage from "@/pages/SynthesisPlannerPage";

function App() {
  return (
    <div className="App min-h-screen bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900">
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<SynthesisPlannerPage />} />
        </Routes>
      </BrowserRouter>
    </div>
  );
}

export default App;
