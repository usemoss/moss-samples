"use client";

import { useDeferredValue, useEffect, useState } from "react";
import { ArrowLeft, ArrowRight, CircleAlert, Database, LoaderCircle, Search } from "lucide-react";
import type { Position, ScoutBrowseResponse } from "../../lib/types";
import { ScoutPlayerCard } from "./moss-search-panel";

const emptyResponse: ScoutBrowseResponse = {
  players: [], page: 1, perPage: 24, total: 0, totalPages: 1, facets: { nations: [], years: [] },
};

export function ArchiveBrowser() {
  const [query, setQuery] = useState("");
  const deferredQuery = useDeferredValue(query);
  const [position, setPosition] = useState<Position | "">("");
  const [nation, setNation] = useState("");
  const [year, setYear] = useState("");
  const [sort, setSort] = useState("rating-desc");
  const [page, setPage] = useState(1);
  const [data, setData] = useState<ScoutBrowseResponse>(emptyResponse);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    const params = new URLSearchParams({ page: String(page), perPage: "24", sort });
    if (deferredQuery.trim()) params.set("query", deferredQuery.trim());
    if (position) params.set("position", position);
    if (nation) params.set("nation", nation);
    if (year) params.set("year", year);
    setLoading(true);
    setError("");
    fetch(`/api/scout/players?${params}`, { signal: controller.signal })
      .then(async (response) => {
        const body = await response.json();
        if (!response.ok) throw new Error(body.error ?? "The archive could not be loaded.");
        setData(body as ScoutBrowseResponse);
      })
      .catch((reason) => {
        if (reason instanceof DOMException && reason.name === "AbortError") return;
        setError(reason instanceof Error ? reason.message : "The archive could not be loaded.");
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [deferredQuery, nation, page, position, sort, year]);

  function resetPage(action: () => void) {
    action();
    setPage(1);
  }

  return (
    <section className="archive-browser">
      <div className="archive-toolbar">
        <div className="archive-query"><Search size={17} /><input value={query} onChange={(event) => resetPage(() => setQuery(event.target.value))} placeholder="Filter by name, nation, year or role…" /></div>
        <select value={position} onChange={(event) => resetPage(() => setPosition(event.target.value as Position | ""))} aria-label="Position"><option value="">Every position</option><option value="GK">Goalkeepers</option><option value="DEF">Defenders</option><option value="MID">Midfielders</option><option value="FWD">Forwards</option></select>
        <select value={nation} onChange={(event) => resetPage(() => setNation(event.target.value))} aria-label="Nation"><option value="">Every nation</option>{data.facets.nations.map((item) => <option key={item} value={item}>{item}</option>)}</select>
        <select value={year} onChange={(event) => resetPage(() => setYear(event.target.value))} aria-label="Tournament"><option value="">Every tournament</option>{data.facets.years.map((item) => <option key={item} value={item}>{item}</option>)}</select>
        <select value={sort} onChange={(event) => resetPage(() => setSort(event.target.value))} aria-label="Sort archive"><option value="rating-desc">Highest rating</option><option value="year-desc">Newest first</option><option value="year-asc">Oldest first</option><option value="name-asc">Player name</option></select>
      </div>
      <div className="archive-result-head"><span><Database size={14} /> {data.total.toLocaleString("en-US")} player campaigns</span><small>Page {data.page} of {data.totalPages}</small></div>
      {error && <div className="inline-error"><CircleAlert size={15} /> {error}</div>}
      {loading ? <div className="archive-loading"><LoaderCircle className="spin-icon" size={24} /> Loading archive…</div> : (
        <div className="archive-player-grid">{data.players.map((player) => <ScoutPlayerCard key={player.id} player={player} />)}</div>
      )}
      {!loading && !data.players.length && <div className="scout-empty"><Search size={24} /><strong>No campaigns found</strong><span>Clear a filter and try again.</span></div>}
      <div className="archive-pagination">
        <button type="button" className="button button-ghost" onClick={() => setPage((value) => Math.max(1, value - 1))} disabled={page <= 1 || loading}><ArrowLeft size={15} /> Previous</button>
        <span>{data.page} / {data.totalPages}</span>
        <button type="button" className="button button-ghost" onClick={() => setPage((value) => Math.min(data.totalPages, value + 1))} disabled={page >= data.totalPages || loading}>Next <ArrowRight size={15} /></button>
      </div>
    </section>
  );
}
