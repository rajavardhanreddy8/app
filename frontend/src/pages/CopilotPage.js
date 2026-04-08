import React, { useState, useRef, useEffect } from "react";
import axios from "axios";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  MessageSquare,
  Send,
  Loader2,
  Bot,
  User,
  Lightbulb,
  Sparkles,
} from "lucide-react";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const suggestedQueries = [
  "How can I reduce the cost of this synthesis?",
  "Increase the yield for an esterification reaction",
  "Suggest a greener alternative solvent",
  "Predict yield for aspirin synthesis",
  "What catalyst should I use for a Suzuki coupling?",
  "How to scale up from lab to pilot?",
];

const CopilotPage = () => {
  const [messages, setMessages] = useState([
    {
      role: "assistant",
      content:
        "Hello! I'm your AI Synthesis Copilot. I can help you optimize reactions, predict yields, suggest conditions, and answer chemistry questions. What would you like to know?",
      timestamp: new Date(),
    },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [routeContext, setRouteContext] = useState("");
  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const sendMessage = async (query) => {
    const messageText = query || input;
    if (!messageText.trim()) return;

    const userMessage = {
      role: "user",
      content: messageText,
      timestamp: new Date(),
    };
    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setLoading(true);

    try {
      const payload = {
        query: messageText,
        context: routeContext ? { route_info: routeContext } : null,
      };

      const response = await axios.post(`${API}/copilot/optimize`, payload);
      const data = response.data;

      let assistantContent = "";
      if (data.action) {
        assistantContent += `**Action:** ${data.action}\n\n`;
      }
      if (data.intent) {
        assistantContent += `**Intent:** ${data.intent}\n\n`;
      }
      if (data.suggestions) {
        assistantContent += `${data.suggestions}\n\n`;
      }
      if (data.estimated_savings) {
        assistantContent += `**Estimated Savings:** ${data.estimated_savings}\n\n`;
      }
      if (data.recommendations && data.recommendations.length > 0) {
        assistantContent += "**Recommendations:**\n";
        data.recommendations.forEach((rec, i) => {
          assistantContent += `${i + 1}. ${rec}\n`;
        });
        assistantContent += "\n";
      }
      if (data.analysis) {
        assistantContent += `**Analysis:** ${data.analysis}\n\n`;
      }
      if (data.yield_prediction) {
        assistantContent += `**Yield Prediction:** ${JSON.stringify(data.yield_prediction)}\n\n`;
      }
      if (data.suggested_conditions) {
        assistantContent += `**Suggested Conditions:**\n`;
        Object.entries(data.suggested_conditions).forEach(([key, val]) => {
          assistantContent += `- ${key}: ${val}\n`;
        });
      }
      if (!assistantContent) {
        assistantContent = JSON.stringify(data, null, 2);
      }

      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: assistantContent,
          timestamp: new Date(),
          raw: data,
        },
      ]);
    } catch (e) {
      console.error("Copilot error:", e);
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: `Sorry, I encountered an error: ${e.response?.data?.detail || e.message}. Please try again.`,
          timestamp: new Date(),
          isError: true,
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const renderMessage = (msg) => {
    const lines = msg.content.split("\n");
    return lines.map((line, i) => {
      if (line.startsWith("**") && line.endsWith("**")) {
        return (
          <p key={i} className="font-bold text-white mt-2">
            {line.replace(/\*\*/g, "")}
          </p>
        );
      }
      if (line.startsWith("**") && line.includes(":**")) {
        const parts = line.split(":**");
        return (
          <p key={i} className="mt-2">
            <span className="font-semibold text-white">
              {parts[0].replace(/\*\*/g, "")}:
            </span>{" "}
            {parts.slice(1).join(":")}
          </p>
        );
      }
      if (line.match(/^\d+\./)) {
        return (
          <p key={i} className="ml-4 text-sm">
            {line}
          </p>
        );
      }
      if (line.startsWith("- ")) {
        return (
          <p key={i} className="ml-4 text-sm">
            • {line.slice(2)}
          </p>
        );
      }
      if (line.trim() === "") return <br key={i} />;
      return (
        <p key={i} className="text-sm">
          {line}
        </p>
      );
    });
  };

  return (
    <div className="max-w-4xl mx-auto h-[calc(100vh-3rem)] flex flex-col">
      {/* Header */}
      <div className="flex items-center gap-3 mb-4">
        <MessageSquare className="w-8 h-8 text-purple-400" />
        <div>
          <h1 className="text-3xl font-bold text-white">AI Copilot</h1>
          <p className="text-purple-200/70 text-sm">
            Natural language synthesis optimization assistant
          </p>
        </div>
      </div>

      {/* Optional context */}
      <Card className="bg-white/5 backdrop-blur-md border-purple-500/20 mb-4">
        <CardContent className="p-3">
          <div className="flex items-center gap-2">
            <Lightbulb className="w-4 h-4 text-yellow-400 flex-shrink-0" />
            <Input
              placeholder="Optional: paste route/reaction context here for more specific advice..."
              value={routeContext}
              onChange={(e) => setRouteContext(e.target.value)}
              className="bg-transparent border-none text-white text-xs placeholder:text-purple-300/40 focus-visible:ring-0"
            />
          </div>
        </CardContent>
      </Card>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto space-y-4 mb-4 pr-2">
        {messages.map((msg, idx) => (
          <div
            key={idx}
            className={`flex gap-3 ${msg.role === "user" ? "justify-end" : ""}`}
          >
            {msg.role === "assistant" && (
              <div className="w-8 h-8 rounded-full bg-purple-600/30 flex items-center justify-center flex-shrink-0">
                <Bot className="w-4 h-4 text-purple-300" />
              </div>
            )}
            <div
              className={`max-w-[80%] rounded-xl px-4 py-3 ${
                msg.role === "user"
                  ? "bg-purple-600/40 text-white"
                  : msg.isError
                  ? "bg-red-500/20 text-red-200 border border-red-500/30"
                  : "bg-white/8 text-purple-100 border border-purple-500/20"
              }`}
            >
              {renderMessage(msg)}
            </div>
            {msg.role === "user" && (
              <div className="w-8 h-8 rounded-full bg-blue-600/30 flex items-center justify-center flex-shrink-0">
                <User className="w-4 h-4 text-blue-300" />
              </div>
            )}
          </div>
        ))}
        {loading && (
          <div className="flex gap-3">
            <div className="w-8 h-8 rounded-full bg-purple-600/30 flex items-center justify-center">
              <Bot className="w-4 h-4 text-purple-300" />
            </div>
            <div className="bg-white/8 rounded-xl px-4 py-3 border border-purple-500/20">
              <Loader2 className="w-5 h-5 animate-spin text-purple-300" />
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Suggested Queries */}
      {messages.length <= 1 && (
        <div className="mb-4">
          <p className="text-purple-300/60 text-xs mb-2 flex items-center gap-1">
            <Sparkles className="w-3 h-3" /> Try asking:
          </p>
          <div className="flex flex-wrap gap-2">
            {suggestedQueries.map((q, i) => (
              <Button
                key={i}
                variant="outline"
                size="sm"
                onClick={() => sendMessage(q)}
                className="bg-purple-500/10 border-purple-500/30 text-purple-200 text-xs hover:bg-purple-500/20"
              >
                {q}
              </Button>
            ))}
          </div>
        </div>
      )}

      {/* Input */}
      <div className="flex gap-2">
        <Input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask about synthesis optimization, conditions, yield..."
          className="flex-1 bg-white/10 border-purple-500/30 text-white placeholder:text-purple-300/40"
          disabled={loading}
        />
        <Button
          onClick={() => sendMessage()}
          disabled={loading || !input.trim()}
          className="bg-purple-600 hover:bg-purple-700 text-white px-6"
        >
          <Send className="w-4 h-4" />
        </Button>
      </div>
    </div>
  );
};

export default CopilotPage;
