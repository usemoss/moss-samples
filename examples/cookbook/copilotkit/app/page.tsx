"use client";

import React, { useState, useEffect } from "react";
import { CopilotKit } from "@copilotkit/react-core";
import { CopilotChat } from "@copilotkit/react-ui";
import { useMossRetrieval } from "./use-moss-retrieval";
import { Shield, Activity, Search, Sparkles, AlertTriangle, Send } from "lucide-react";

// Inner component to access the CopilotKit hook and handle dashboard logic
function DashboardContent() {
  const [logs, setLogs] = useState<string[]>([
    "System: CopilotKit initialized.",
    "System: Moss retrieval action registered.",
    "System: Ready to ground answers in knowledge base."
  ]);
  const [checkStatus, setCheckStatus] = useState<{
    mode: "mock" | "real" | "unknown";
    warning?: string;
  }>({ mode: "unknown" });

  // Add a log entry helper
  const addLog = (message: string) => {
    const timestamp = new Date().toLocaleTimeString();
    setLogs((prev) => [...prev, `[${timestamp}] ${message}`]);
  };

  // Register the useMossRetrieval hook.
  // When CopilotKit needs knowledge, this action fires and pushes logs to our status feed.
  useMossRetrieval({
    topK: 3,
    onSearchStart: (query) => {
      addLog(`🔍 Agent triggered Moss search: "${query}"`);
    },
    onSearchComplete: (data) => {
      const modeText = data.mode === "mock" ? "MOCK database" : "REAL Moss Cloud";
      const docCount = data.docs?.length || 0;
      addLog(`✅ Moss returned ${docCount} documents from ${modeText}.`);
      if (data.docs && data.docs.length > 0) {
        data.docs.forEach((doc: any, i: number) => {
          addLog(`   └─ Doc #${i + 1} (${doc.id}): "${doc.text.slice(0, 60)}..." (Score: ${doc.score.toFixed(2)})`);
        });
      }
    },
  });

  // Verify backend integration mode (mock vs real)
  useEffect(() => {
    const checkBackendStatus = async () => {
      try {
        const res = await fetch("/api/moss/query?query=test");
        const data = await res.json().catch(() => ({}));

        if (!res.ok) {
          const errorMessage = data?.error || `Moss backend returned ${res.status}`;
          setCheckStatus({ mode: "unknown", warning: errorMessage });
          addLog(`System Error: Failed to check Moss backend status: ${errorMessage}`);
          return;
        }

        if (data.mode) {
          setCheckStatus({
            mode: data.mode,
            warning: data.warning,
          });
          addLog(`System: Server running in ${data.mode.toUpperCase()} mode.`);
          if (data.warning) {
            addLog(`Warning: ${data.warning}`);
          }
        }
      } catch (err: any) {
        addLog(`System Error: Failed to check Moss backend status: ${err.message || String(err)}`);
      }
    };

    void checkBackendStatus();
  }, []);

  // Direct Moss Search Sandbox State
  const [sandboxQuery, setSandboxQuery] = useState("");
  const [sandboxResults, setSandboxResults] = useState<any[]>([]);
  const [isSandboxSearching, setIsSandboxSearching] = useState(false);

  const handleSandboxSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!sandboxQuery.trim()) return;

    setIsSandboxSearching(true);
    try {
      const res = await fetch(`/api/moss/query?query=${encodeURIComponent(sandboxQuery)}&topK=3`);
      const data = await res.json();
      setSandboxResults(data.docs || []);
      addLog(`Sandbox: Manual query completed for "${sandboxQuery}"`);
    } catch (err: any) {
      addLog(`Sandbox Error: Manual query failed: ${err.message}`);
    } finally {
      setIsSandboxSearching(false);
    }
  };

  return (
    <div className="container">
      {/* Header */}
      <header className="header">
        <div className="badge-container">
          <span className="badge badge-active">Integration Cookbook</span>
          <span className={`badge ${checkStatus.mode === 'real' ? 'badge-active' : ''}`}>
            {checkStatus.mode === "unknown"
              ? "Checking backend status..."
              : checkStatus.mode === "real"
              ? "Connected to Moss Cloud"
              : "Running in Mock Mode"}
          </span>
        </div>
        <h1 className="title">Moss + CopilotKit</h1>
        <p className="subtitle">
          Ground CopilotKit in-app AI agents with Moss&apos;s sub-10ms semantic search runtime to answer user questions using internal knowledge.
        </p>
      </header>

      {/* Main Grid */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "2rem", width: "100%" }}>
        
        {/* Left Column: Developer Dashboard & Moss Sandbox */}
        <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
          
          {/* Status Panel */}
          <div className="panel">
            <h2 style={{ fontSize: "1.2rem", marginBottom: "1rem", display: "flex", alignItems: "center", gap: "0.5rem" }}>
              <Shield size={20} color="#45f3ff" />
              Developer Control Room
            </h2>
            
            {checkStatus.mode === "mock" && (
              <div style={{
                background: "rgba(245, 158, 11, 0.1)",
                border: "1px solid rgba(245, 158, 11, 0.2)",
                padding: "0.85rem",
                borderRadius: "0.75rem",
                fontSize: "0.85rem",
                color: "#f59e0b",
                marginBottom: "1.5rem",
                display: "flex",
                gap: "0.5rem"
              }}>
                <AlertTriangle size={18} style={{ flexShrink: 0 }} />
                <div>
                  <strong>Running in Mock Mode.</strong> Mock documents (Refund Policy, Office Hours, Support Contact, Moss Info) will be searched server-side via <code>/api/moss/query</code>. Add your credentials to <code>.env</code> to test real indexes.
                </div>
              </div>
            )}

            <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem", fontSize: "0.9rem" }}>
              <div style={{ display: "flex", justifyContent: "space-between", borderBottom: "1px solid var(--border-color)", paddingBottom: "0.5rem" }}>
                <span>Moss API Status</span>
                <span style={{ color: checkStatus.mode === 'real' ? "var(--success)" : "#f59e0b", fontWeight: 600 }}>
                  {checkStatus.mode === 'real' ? "Active (Real Mode)" : "Simulated (Mock Mode)"}
                </span>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between", borderBottom: "1px solid var(--border-color)", paddingBottom: "0.5rem" }}>
                <span>Backend Port</span>
                <span>3000 (Next.js server)</span>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span>LLM Service</span>
                <span>OpenAI GPT-4o / CopilotKit Agent</span>
              </div>
            </div>
          </div>

          {/* Manual Moss Query Sandbox */}
          <div className="panel">
            <h2 style={{ fontSize: "1.2rem", marginBottom: "1rem", display: "flex", alignItems: "center", gap: "0.5rem" }}>
              <Search size={20} color="#45f3ff" />
              Direct Moss Query Sandbox
            </h2>
            <p style={{ fontSize: "0.85rem", color: "var(--text-secondary)", marginBottom: "1.25rem" }}>
              Run queries directly against the Moss index endpoint to verify matches without using the LLM.
            </p>

            <form onSubmit={handleSandboxSearch} style={{ display: "flex", gap: "0.5rem", marginBottom: "1.25rem" }}>
              <input
                type="text"
                placeholder="Type query (e.g. refund, support)..."
                value={sandboxQuery}
                onChange={(e) => setSandboxQuery(e.target.value)}
                className="input"
                style={{ flex: 1 }}
              />
              <button type="submit" className="btn btn-primary" disabled={isSandboxSearching}>
                <Send size={16} />
              </button>
            </form>

            {/* Sandbox Results */}
            <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem", maxHeight: "200px", overflowY: "auto" }}>
              {sandboxResults.length > 0 ? (
                sandboxResults.map((doc, idx) => (
                  <div key={idx} style={{ background: "rgba(255, 255, 255, 0.03)", border: "1px solid var(--border-color)", borderRadius: "0.5rem", padding: "0.75rem" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "0.25rem", fontSize: "0.75rem" }}>
                      <span style={{ color: "var(--accent)", fontWeight: 600 }}>{doc.id}</span>
                      <span style={{ color: "var(--success)" }}>Score: {doc.score.toFixed(2)}</span>
                    </div>
                    <p style={{ fontSize: "0.8rem", color: "var(--text-primary)" }}>{doc.text}</p>
                  </div>
                ))
              ) : (
                <div style={{ textAlign: "center", padding: "1.5rem", color: "var(--text-muted)", fontSize: "0.85rem", background: "rgba(255, 255, 255, 0.01)", borderRadius: "0.5rem", border: "1px dashed var(--border-color)" }}>
                  No manual query results yet.
                </div>
              )}
            </div>
          </div>

          {/* Event Stream Terminal */}
          <div className="panel" style={{ flexGrow: 1 }}>
            <h2 style={{ fontSize: "1.2rem", marginBottom: "1rem", display: "flex", alignItems: "center", gap: "0.5rem" }}>
              <Activity size={20} color="#45f3ff" />
              Retrieval Event Terminal
            </h2>
            <div className="status-feed">
              {logs.map((log, index) => (
                <div key={index} className="status-line">{log}</div>
              ))}
            </div>
          </div>

        </div>

        {/* Right Column: CopilotKit Chat Assistant */}
        <div style={{ display: "flex", flexDirection: "column" }}>
          <div className="panel" style={{ height: "100%", display: "flex", flexDirection: "column" }}>
            <h2 style={{ fontSize: "1.2rem", marginBottom: "0.5rem", display: "flex", alignItems: "center", gap: "0.5rem" }}>
              <Sparkles size={20} color="#45f3ff" />
              Grounded Chat Assistant
            </h2>
            <p style={{ fontSize: "0.85rem", color: "var(--text-secondary)", marginBottom: "1.5rem" }}>
              Ask questions about refunds, office location, support contacts, or Moss. The agent will fetch relevant details to answer.
            </p>

            <div className="chat-container" style={{ flexGrow: 1 }}>
              <CopilotChat
                labels={{
                  title: "Knowledge Base Copilot",
                  initial: "Hi! I am grounded in your Moss knowledge base. Ask me anything about our policies, office, contact details, or Moss itself!",
                }}
              />
            </div>
          </div>
        </div>

      </div>
    </div>
  );
}

export default function Home() {
  return (
    <main>
      <div className="bg-gradient"></div>
      
      {/* 
        Wrap our application in the CopilotKit Provider. 
        It connects to our API route runtime handler (/api/copilotkit), 
        which coordinates LLM calls and executes registered actions.
      */}
      <CopilotKit runtimeUrl="/api/copilotkit">
        <DashboardContent />
      </CopilotKit>

      <footer style={{ marginTop: "3rem", fontSize: "0.75rem", color: "var(--text-muted)", textAlign: "center" }}>
        MOSS + COPILOTKIT INTEGRATION COOKBOOK • MADE WITH LOVE BY DEEPMIND ANTIGRAVITY
      </footer>
    </main>
  );
}
