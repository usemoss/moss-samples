"use client";

import { useEffect, useMemo, useState } from "react";
import { ArrowRight, CircleAlert, Dices, Filter, LoaderCircle, Search, Sparkles, Target, Trophy, Users } from "lucide-react";
import { FORMATIONS } from "../../lib/formations";
import type { DraftPlayer, EraTournament } from "../../lib/types";
import { useGameStore } from "../../store/game-store";
import { MossSearchPanel } from "../scout/moss-search-panel";
import { Pitch } from "./pitch";

export function EraSpinPhase() {
  const setEraYear = useGameStore((state) => state.setEraYear);
  const reset = useGameStore((state) => state.reset);
  const picks = useGameStore((state) => state.picks);
  const usedEraYears = useGameStore((state) => state.usedEraYears);
  const [spinning, setSpinning] = useState(false);
  const [preview, setPreview] = useState<EraTournament | null>(null);
  const [error, setError] = useState("");

  async function spin() {
    setSpinning(true);
    setPreview(null);
    setError("");
    try {
      const request = fetch(`/api/eras?year=random&used=${encodeURIComponent(usedEraYears.join(","))}`, { cache: "no-store" }).then(async (response) => {
        const body = await response.json();
        if (!response.ok) throw new Error(body.error ?? "The era wheel could not find a tournament.");
        return body as EraTournament;
      });
      const [tournament] = await Promise.all([request, new Promise((resolve) => setTimeout(resolve, 1450))]);
      setPreview(tournament);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "The era wheel failed.");
    } finally {
      setSpinning(false);
    }
  }

  return (
    <section className="era-spin-phase">
      <div className="era-spin-copy">
        <span className="step-tag">02 / Era pick {picks.length + 1} of 11</span>
        <h1>Spin a year.<br />Choose one.</h1>
        <p>Every pick starts with a new World Cup year. Open that tournament’s complete roster, take one eligible player, then return here and spin again for the next position.</p>
        {usedEraYears.length > 0 && <div className="used-era-row"><span>Years already drafted</span><div>{usedEraYears.map((year) => <b key={year}>{year}</b>)}</div></div>}
        <button type="button" className="text-button" onClick={reset}>Change formation</button>
      </div>
      <div className="era-wheel-card">
        <div className={`wheel era-wheel ${spinning ? "spinning" : ""}`}>
          <div className="wheel-ring" />
          <div className="wheel-core"><span>{preview?.year ?? (spinning ? "?" : picks.length + 1)}</span><small>{preview ? "WORLD CUP" : spinning ? "TURNING" : "NEXT PICK"}</small></div>
          <i className="wheel-pointer" />
        </div>
        {preview ? (
          <div className="era-reveal">
            <span className="eyebrow">Pick {picks.length + 1} player pool</span>
            <h2>{preview.year} World Cup</h2>
            <div><span><Trophy size={15} /> {preview.squads} countries</span><span><Users size={15} /> {preview.players} players</span></div>
            <button type="button" className="button button-primary button-large" onClick={() => setEraYear(preview.year)}>Choose one from {preview.year} <ArrowRight size={18} /></button>
            <button type="button" className="text-button" onClick={spin}>Spin again</button>
          </div>
        ) : (
          <>
            <h2>{spinning ? "Football history is turning…" : `Spin for player ${picks.length + 1}`}</h2>
            <p>Unused tournaments from Uruguay 1930 to Qatar 2022 have an equal chance.</p>
            {error && <div className="inline-error"><CircleAlert size={15} /> {error}</div>}
            <button type="button" className="button button-primary button-large" onClick={spin} disabled={spinning}>
              {spinning ? <LoaderCircle className="spin-icon" size={18} /> : <Dices size={18} />} {spinning ? "Spinning" : "Spin the era wheel"}
            </button>
          </>
        )}
      </div>
    </section>
  );
}

export function EraDraftPhase() {
  const formation = useGameStore((state) => state.formation);
  const eraYear = useGameStore((state) => state.eraYear);
  const picks = useGameStore((state) => state.picks);
  const assignEraPlayer = useGameStore((state) => state.assignEraPlayer);
  const reset = useGameStore((state) => state.reset);
  const [tournament, setTournament] = useState<EraTournament | null>(null);
  const [selectedPlayer, setSelectedPlayer] = useState<DraftPlayer | null>(null);
  const [nation, setNation] = useState("");
  const [query, setQuery] = useState("");
  const [tab, setTab] = useState<"browse" | "moss">("browse");
  const [error, setError] = useState("");

  useEffect(() => {
    if (!eraYear) return;
    let active = true;
    fetch(`/api/eras?year=${eraYear}`, { cache: "no-store" })
      .then(async (response) => {
        const body = await response.json();
        if (!response.ok) throw new Error(body.error ?? "Could not open that tournament archive.");
        if (active) setTournament(body as EraTournament);
      })
      .catch((reason) => active && setError(reason instanceof Error ? reason.message : "Could not load the tournament."));
    return () => { active = false; };
  }, [eraYear]);

  const allPlayers = useMemo(() => tournament?.historicSquads.flatMap((squad) => squad.players) ?? [], [tournament]);
  const openPositions = useMemo(() => {
    const filled = new Set(picks.map((pick) => pick.slotId));
    return new Set(FORMATIONS[formation].filter((slot) => !filled.has(slot.id)).map((slot) => slot.position));
  }, [formation, picks]);
  const pickedIds = useMemo(() => new Set(picks.map((pick) => pick.player.id)), [picks]);
  const filteredPlayers = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    return allPlayers
      .filter((player) => (!nation || player.nation === nation) && openPositions.has(player.position))
      .filter((player) => !normalized || `${player.name} ${player.nation} ${player.position} ${player.subPosition}`.toLowerCase().includes(normalized))
      .sort((a, b) => b.rating - a.rating || a.name.localeCompare(b.name));
  }, [allPlayers, nation, openPositions, query]);

  function choose(player: DraftPlayer) {
    if (pickedIds.has(player.id) || !openPositions.has(player.position)) return;
    setSelectedPlayer(player);
  }

  function assign(slotId: string) {
    if (!selectedPlayer) return;
    assignEraPlayer(selectedPlayer, slotId);
    setSelectedPlayer(null);
  }

  if (!tournament && !error) return <section className="simulation-loading"><span className="loader-ring" /><span className="step-tag">03 / World Cup Era</span><h1>Opening {eraYear}…</h1><p>Loading every country and player from the tournament.</p></section>;
  if (error) return <section className="simulation-loading"><CircleAlert size={30} /><h1>Archive unavailable.</h1><p>{error}</p><button className="button button-primary" onClick={reset}>Spin another year</button></section>;

  return (
    <section className="era-draft-layout">
      <aside className="era-draft-sidebar">
        <span className="step-tag">03 / Era pick {picks.length + 1} of 11</span>
        <div className="era-year-lock"><strong>{eraYear}</strong><small>{tournament?.squads} countries · {tournament?.players} players</small></div>
        <div className="progress-track"><span style={{ width: `${(picks.length / 11) * 100}%` }} /></div>
        <p>{selectedPlayer ? `Place ${selectedPlayer.name} into a glowing ${selectedPlayer.position} slot.` : "Browse the tournament or ask Moss for a recommendation."}</p>
        <Pitch formation={formation} picks={picks} selectedPlayer={selectedPlayer} onAssign={assign} compact />
        <div className="selection-hint"><Target size={15} /> Choose exactly one {eraYear} player · {11 - picks.length} slots left</div>
        <button type="button" className="text-button" onClick={reset}>Restart Era mode</button>
      </aside>
      <div className="era-roster-workspace">
        <div className="era-tabs" role="tablist" aria-label="Era player discovery">
          <button role="tab" aria-selected={tab === "browse"} className={tab === "browse" ? "active" : ""} onClick={() => setTab("browse")}><Users size={16} /> Browse {eraYear} roster</button>
          <button role="tab" aria-selected={tab === "moss"} className={tab === "moss" ? "active" : ""} onClick={() => setTab("moss")}><Sparkles size={16} /> Search this wheel roster</button>
        </div>
        <div hidden={tab !== "moss"}>
          <MossSearchPanel
              lockedYear={eraYear ?? undefined}
              scopeLabel={`${eraYear} WORLD CUP ONLY`}
              onChoose={choose}
              selectedPlayerId={selectedPlayer?.id}
              excludedPlayerIds={picks.map((pick) => pick.player.id)}
              allowedPositions={[...openPositions]}
              actionLabel="Select for XI"
            />
        </div>
        <section className="era-browser" hidden={tab !== "browse"}>
            <div className="era-browser-toolbar">
              <label className="era-player-search"><Search size={17} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder={`Search ${eraYear} players…`} /></label>
              <label><Filter size={15} /><select value={nation} onChange={(event) => setNation(event.target.value)}><option value="">Every country</option>{tournament?.historicSquads.map((squad) => <option key={squad.id} value={squad.nation}>{squad.nation}</option>)}</select></label>
            </div>
            <div className="era-browser-summary"><span>{filteredPlayers.length} eligible players</span><small>Only positions still open in your {formation} are shown</small></div>
            <div className="era-player-grid">
              {filteredPlayers.map((player) => {
                const picked = pickedIds.has(player.id);
                return <button key={player.id} type="button" className={`player-card ${selectedPlayer?.id === player.id ? "selected" : ""}`} onClick={() => choose(player)} disabled={picked}>
                  <div className="player-rating"><strong>{player.rating}</strong><span>{player.subPosition}</span></div>
                  <div className="player-card-copy"><strong>{player.name}</strong><small>{player.nation} · {player.inputs.appearances} apps · {player.inputs.goals} goals</small></div>
                  <span className="card-chevron">{picked ? "IN XI" : player.position}</span>
                </button>;
              })}
            </div>
        </section>
      </div>
    </section>
  );
}
