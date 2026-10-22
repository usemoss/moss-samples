"use client";

import { useState } from "react";
import { Database, Search, Sparkles, Zap } from "lucide-react";
import { ArchiveBrowser } from "./archive-browser";
import { MossSearchPanel } from "./moss-search-panel";
import { MossCredentialsProvider } from "./moss-credentials-context";

export function ScoutLabClient() {
  const [mode, setMode] = useState<"moss" | "archive">("moss");
  return (
    <MossCredentialsProvider>
    <main className="scout-lab-main">
      <section className="scout-lab-hero">
        <div className="scout-grid-lines" />
        <div className="shell scout-hero-inner">
          <div>
            <span className="hero-tag"><i /> POWERED BY MOSS</span>
            <h1>Ask history.<br /><em>Find your player.</em></h1>
            <p>Search 10,973 World Cup player campaigns by meaning, or browse every record directly. This lab never changes your active draft.</p>
          </div>
          <div className="scout-lab-stats">
            <div><Zap size={18} /><strong>10,973</strong><span>searchable campaigns</span></div>
            <div><Sparkles size={18} /><strong>22</strong><span>World Cups</span></div>
            <div><Database size={18} /><strong>489</strong><span>historic squads</span></div>
          </div>
        </div>
      </section>
      <section className="shell scout-lab-content">
        <div className="scout-mode-tabs" role="tablist" aria-label="Scout Lab mode">
          <button type="button" role="tab" aria-selected={mode === "moss"} className={mode === "moss" ? "active" : ""} onClick={() => setMode("moss")}><Search size={16} /> Moss semantic search</button>
          <button type="button" role="tab" aria-selected={mode === "archive"} className={mode === "archive" ? "active" : ""} onClick={() => setMode("archive")}><Database size={16} /> Archive browse</button>
        </div>
        {mode === "moss" ? <MossSearchPanel /> : <ArchiveBrowser />}
      </section>
    </main>
    </MossCredentialsProvider>
  );
}
