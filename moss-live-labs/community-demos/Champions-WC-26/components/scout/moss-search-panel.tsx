"use client";

import { FormEvent, useState } from "react";
import { ArrowRight, Check, CircleAlert, Eye, EyeOff, KeyRound, LoaderCircle, Search, Sparkles, Unplug } from "lucide-react";
import type { ClassicRatingMode, DraftPlayer, Position, ScoutSearchHit } from "../../lib/types";
import { useMossCredentials } from "./moss-credentials-context";

const suggestions = [
  "Creative midfielder from an underdog run",
  "Commanding goalkeeper before 1990",
  "Left-sided attacker from an African knockout team",
  "High-scoring defender from a finalist",
  "Someone similar to Zidane 1998",
];

type MossSearchPanelProps = {
  onChoose?: (player: DraftPlayer) => void;
  selectedPlayerId?: string;
  excludedPlayerIds?: string[];
  actionLabel?: string;
  compactIntro?: boolean;
  lockedYear?: number;
  scopeLabel?: string;
  allowedPositions?: Position[];
  ratingMode?: ClassicRatingMode;
};

type ConnectionInfo = {
  created: boolean;
  count: number;
  indexName: string;
  loadTimeMs: number;
};

type SearchResponse = {
  hits: ScoutSearchHit[];
  timeTakenMs: number;
  indexName: string;
};

export function ScoutPlayerCard({
  player,
  hit,
  onChoose,
  selected = false,
  disabled = false,
  actionLabel = "Choose player",
  disabledLabel = "Already in your XI",
}: {
  player: DraftPlayer;
  hit?: ScoutSearchHit;
  onChoose?: () => void;
  selected?: boolean;
  disabled?: boolean;
  actionLabel?: string;
  disabledLabel?: string;
}) {
  return (
    <article className={`scout-player-card ${selected ? "selected" : ""}`}>
      <div className="scout-card-rating"><strong>{player.rating}</strong><small>{player.ratingMode === "prime" ? "PRIME" : "OVR"}</small></div>
      <div className="scout-card-main">
        <div className="scout-card-heading">
          <div><span>{player.nationCode} · {player.year}</span><h3>{player.name}</h3></div>
          <b>{player.subPosition}</b>
        </div>
        <div className="scout-stat-row">
          <span><strong>{player.inputs.appearances}</strong> Apps</span>
          <span><strong>{player.inputs.goals}</strong> Goals</span>
          <span><strong>{player.inputs.teamFinish}</strong> Finish</span>
        </div>
        {hit && <p>{hit.explanation}</p>}
        {hit && <div className="moss-score"><span style={{ width: `${Math.max(3, Math.min(100, hit.score * 100))}%` }} /><small>{Math.round(hit.score * 100)}% Moss match</small></div>}
        {onChoose && (
          <button type="button" className="scout-card-action" onClick={onChoose} disabled={disabled}>
            {disabled ? disabledLabel : selected ? <><Check size={14} /> Selected</> : <>{actionLabel} <ArrowRight size={14} /></>}
          </button>
        )}
      </div>
    </article>
  );
}

export function MossSearchPanel({ onChoose, selectedPlayerId, excludedPlayerIds = [], actionLabel, compactIntro = false, lockedYear, scopeLabel, allowedPositions, ratingMode = "campaign" }: MossSearchPanelProps) {
  const { projectId, projectKey, setProjectId, setProjectKey, clearCredentials } = useMossCredentials();
  const [showKey, setShowKey] = useState(false);
  const [connected, setConnected] = useState(false);
  const [connection, setConnection] = useState<ConnectionInfo | null>(null);
  const [query, setQuery] = useState("");
  const [position, setPosition] = useState<Position | "">("");
  const [results, setResults] = useState<SearchResponse | null>(null);
  const [loading, setLoading] = useState<"connect" | "search" | null>(null);
  const [error, setError] = useState("");
  const excluded = new Set(excludedPlayerIds);

  async function callMoss(payload: Record<string, unknown>) {
    const response = await fetch("/api/scout/moss", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ ...payload, projectId, projectKey }),
    });
    const body = await response.json();
    if (!response.ok) throw new Error(body.error ?? "Moss Scout could not complete the request.");
    return body;
  }

  async function connect(event: FormEvent) {
    event.preventDefault();
    if (!projectId.trim() || !projectKey.trim()) return;
    setLoading("connect");
    setError("");
    try {
      const body = await callMoss({ action: "connect" }) as ConnectionInfo;
      setConnection(body);
      setConnected(true);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Moss Scout could not connect.");
    } finally {
      setLoading(null);
    }
  }

  async function search(event?: FormEvent, suggestedQuery?: string) {
    event?.preventDefault();
    const nextQuery = (suggestedQuery ?? query).trim();
    if (!nextQuery || !connected) return;
    if (suggestedQuery) setQuery(suggestedQuery);
    setLoading("search");
    setError("");
    try {
      const body = await callMoss({ action: "search", query: nextQuery, position: position || undefined, year: lockedYear, ratingMode }) as SearchResponse;
      setResults(body);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Moss Scout could not search.");
    } finally {
      setLoading(null);
    }
  }

  function changeCredentials() {
    setConnected(false);
    setConnection(null);
    setResults(null);
    clearCredentials();
    setError("");
  }

  if (!connected) {
    return (
      <section className="moss-connect-card">
        <div className="moss-connect-mark"><KeyRound size={22} /></div>
        <div className="moss-connect-copy">
          <span className="eyebrow">Connect your Moss project</span>
          <h2>{compactIntro ? "Unlock your one scout transfer." : lockedYear ? `Search every ${lockedYear} player with Moss.` : "Search the full World Cup archive with Moss."}</h2>
          <p>The first connection creates a dedicated <strong>moss-minilm</strong> index containing all 10,973 player campaigns. {lockedYear ? `Every result here is filtered to the ${lockedYear} tournament.` : "Later searches reuse that index."}</p>
        </div>
        <form className="moss-credentials-form" onSubmit={connect}>
          <label>
            <span>Project ID</span>
            <input value={projectId} onChange={(event) => setProjectId(event.target.value)} placeholder="Your Moss project ID" autoComplete="off" spellCheck={false} />
          </label>
          <label>
            <span>Project key</span>
            <div className="secret-input">
              <input type={showKey ? "text" : "password"} value={projectKey} onChange={(event) => setProjectKey(event.target.value)} placeholder="Your Moss project key" autoComplete="new-password" spellCheck={false} />
              <button type="button" onClick={() => setShowKey(!showKey)} aria-label={showKey ? "Hide project key" : "Show project key"}>{showKey ? <EyeOff size={16} /> : <Eye size={16} />}</button>
            </div>
          </label>
          <div className="credential-note"><KeyRound size={13} /> Credentials stay out of browser storage and the game database.</div>
          {error && <div className="inline-error"><CircleAlert size={15} /> {error}</div>}
          <button type="submit" className="button button-primary button-large" disabled={!projectId.trim() || !projectKey.trim() || loading === "connect"}>
            {loading === "connect" ? <LoaderCircle className="spin-icon" size={18} /> : <Sparkles size={18} />}
            {loading === "connect" ? "Preparing 10,973 campaigns…" : "Connect Moss Scout"}
          </button>
          {loading === "connect" && <small className="first-index-note">The first index build can take a little while. Keep this page open.</small>}
        </form>
      </section>
    );
  }

  return (
    <section className="moss-search-workspace">
      <div className="moss-status-row">
        <span><i /> MOSS CONNECTED · {scopeLabel ?? (lockedYear ? `${lockedYear} WORLD CUP ONLY` : `${connection?.count.toLocaleString("en-US")} CAMPAIGNS`)}</span>
        <button type="button" onClick={changeCredentials}><Unplug size={13} /> Change credentials</button>
      </div>
      <form className="moss-search-form" onSubmit={(event) => search(event)}>
        <div className="moss-query-field"><Search size={19} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Describe the player or campaign you need…" /></div>
        <select value={position} onChange={(event) => setPosition(event.target.value as Position | "")} aria-label="Filter Moss search by position">
          <option value="">All positions</option>
          <option value="GK" disabled={allowedPositions ? !allowedPositions.includes("GK") : false}>Goalkeepers</option>
          <option value="DEF" disabled={allowedPositions ? !allowedPositions.includes("DEF") : false}>Defenders</option>
          <option value="MID" disabled={allowedPositions ? !allowedPositions.includes("MID") : false}>Midfielders</option>
          <option value="FWD" disabled={allowedPositions ? !allowedPositions.includes("FWD") : false}>Forwards</option>
        </select>
        <button type="submit" className="button button-primary" disabled={!query.trim() || loading === "search"}>
          {loading === "search" ? <LoaderCircle className="spin-icon" size={17} /> : <Search size={17} />}
          {loading === "search" ? "Searching" : "Scout"}
        </button>
      </form>
      <div className="scout-suggestions">
        {suggestions.map((suggestion) => <button type="button" key={suggestion} onClick={() => search(undefined, suggestion)} disabled={loading === "search"}>{suggestion}</button>)}
      </div>
      {error && <div className="inline-error moss-error"><CircleAlert size={15} /> {error}</div>}
      {results && (
        <div className="moss-results-head">
          <div><span className="eyebrow">Moss found {results.hits.length}</span><h2>Scouting report</h2></div>
          <small>{results.timeTakenMs.toFixed(1)} ms local query</small>
        </div>
      )}
      {results && !results.hits.length && <div className="scout-empty"><Search size={24} /><strong>No matching campaigns</strong><span>Try a broader description or remove the position filter.</span></div>}
      {results && results.hits.length > 0 && (
        <div className="scout-result-grid">
          {results.hits.map((hit) => (
            <ScoutPlayerCard
              key={hit.player.id}
              player={hit.player}
              hit={hit}
              selected={selectedPlayerId === hit.player.id}
              disabled={excluded.has(hit.player.id) || (allowedPositions ? !allowedPositions.includes(hit.player.position) : false)}
              disabledLabel={excluded.has(hit.player.id) ? "Already in your XI" : "That position is filled"}
              onChoose={onChoose ? () => onChoose(hit.player) : undefined}
              actionLabel={actionLabel}
            />
          ))}
        </div>
      )}
      {!results && <div className="moss-ready-state"><Sparkles size={25} /><strong>Ask for football qualities, not database fields.</strong><span>Moss searches the meaning of every campaign description, then returns the closest historical matches.</span></div>}
    </section>
  );
}
