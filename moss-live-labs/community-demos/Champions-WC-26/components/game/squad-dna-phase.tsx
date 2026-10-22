"use client";

import { useState } from "react";
import { ArrowRight, CircleAlert, Dna, Eye, EyeOff, KeyRound, LoaderCircle, Sparkles } from "lucide-react";
import type { SquadDnaResult } from "../../lib/types";
import { useGameStore } from "../../store/game-store";
import { useMossCredentials } from "../scout/moss-credentials-context";
import { Pitch } from "./pitch";

export function SquadDnaPhase() {
  const formation = useGameStore((state) => state.formation);
  const gameMode = useGameStore((state) => state.gameMode);
  const picks = useGameStore((state) => state.picks);
  const squadDna = useGameStore((state) => state.squadDna);
  const setSquadDna = useGameStore((state) => state.setSquadDna);
  const finishDna = useGameStore((state) => state.finishDna);
  const skipDna = useGameStore((state) => state.skipDna);
  const { projectId, projectKey, setProjectId, setProjectKey } = useMossCredentials();
  const [showKey, setShowKey] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [queryTime, setQueryTime] = useState<number | null>(null);

  async function analyze() {
    if (!projectId.trim() || !projectKey.trim()) return;
    setLoading(true);
    setError("");
    try {
      const response = await fetch("/api/scout/moss", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ action: "dna", projectId, projectKey, xi: picks }),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body.error ?? "Squad DNA could not analyze this XI.");
      setSquadDna(body.result as SquadDnaResult);
      setQueryTime(typeof body.timeTakenMs === "number" ? body.timeTakenMs : null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Squad DNA failed.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="dna-layout">
      <aside className="dna-xi-panel">
        <span className="step-tag">{gameMode === "classic" ? "05" : "04"} / Squad DNA</span>
        <h1>What team does<br />your XI feel like?</h1>
        <p>Moss searches 489 historical World Cup squads, while a football profile compares attack, defense, goalkeeper quality, tournament experience and balance.</p>
        <Pitch formation={formation} picks={picks} compact />
      </aside>
      <div className="dna-workspace">
        {squadDna ? (
          <section className="dna-reveal-card">
            <span className="dna-kicker"><Sparkles size={15} /> CLOSEST HISTORICAL DNA</span>
            <div className="dna-match-lockup"><div><small>{squadDna.match.nationCode}</small><strong>{squadDna.match.year}</strong></div><h2>{squadDna.match.nation}<br /><em>{squadDna.match.year}</em></h2><span>{squadDna.similarity}%<small>match</small></span></div>
            <p>{squadDna.explanation}</p>
            <div className="dna-comparison-grid">
              <div><span>Metric</span><b>Your XI</b><b>{squadDna.match.nationCode} {squadDna.match.year}</b></div>
              <div><span>Overall</span><b>{squadDna.custom.rating}</b><b>{squadDna.match.rating}</b></div>
              <div><span>Attack</span><b>{squadDna.custom.attack}</b><b>{squadDna.match.attack}</b></div>
              <div><span>Defense</span><b>{squadDna.custom.defense}</b><b>{squadDna.match.defense}</b></div>
              <div><span>Goalkeeper</span><b>{squadDna.custom.goalkeeper}</b><b>{squadDna.match.goalkeeper}</b></div>
              <div><span>Experience</span><b>{squadDna.custom.experience}</b><b>{squadDna.match.experience}</b></div>
              <div><span>Era center</span><b>{squadDna.custom.averageYear}</b><b>{squadDna.match.year}</b></div>
              <div><span>National mix</span><b>{squadDna.custom.nations} nations</b><b>{squadDna.match.nation}</b></div>
            </div>
            {queryTime !== null && <small className="dna-query-time">Moss local query: {queryTime.toFixed(1)} ms · historical finish: {squadDna.match.finish}</small>}
            <button type="button" className="button button-primary button-large" onClick={finishDna}>Continue to the tournament <ArrowRight size={18} /></button>
          </section>
        ) : (
          <section className="dna-connect-card">
            <div className="dna-icon"><Dna size={32} /></div>
            <span className="eyebrow">Powered by Moss</span>
            <h2>Reveal your closest historical squad.</h2>
            <p>The first reveal creates a separate <strong>489-squad Moss index</strong>. Your key is sent only to this server request and is never saved in browser storage or the game database.</p>
            <div className="dna-credentials">
              <label><span>Project ID</span><input value={projectId} onChange={(event) => setProjectId(event.target.value)} placeholder="Your Moss project ID" autoComplete="off" /></label>
              <label><span>Project key</span><div className="secret-input"><input type={showKey ? "text" : "password"} value={projectKey} onChange={(event) => setProjectKey(event.target.value)} placeholder="Your Moss project key" autoComplete="new-password" /><button type="button" onClick={() => setShowKey(!showKey)} aria-label={showKey ? "Hide project key" : "Show project key"}>{showKey ? <EyeOff size={16} /> : <Eye size={16} />}</button></div></label>
            </div>
            <div className="credential-note"><KeyRound size={13} /> The same in-memory credentials carry over from Era search or Classic Scout.</div>
            {error && <div className="inline-error"><CircleAlert size={15} /> {error}</div>}
            <button type="button" className="button button-primary button-large" onClick={analyze} disabled={!projectId.trim() || !projectKey.trim() || loading}>{loading ? <LoaderCircle className="spin-icon" size={18} /> : <Sparkles size={18} />}{loading ? "Searching 489 squads…" : "Reveal Squad DNA"}</button>
            <button type="button" className="text-button" onClick={skipDna}>Continue without Squad DNA</button>
          </section>
        )}
      </div>
    </section>
  );
}
