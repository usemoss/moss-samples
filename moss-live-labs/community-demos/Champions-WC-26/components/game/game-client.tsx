"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowRight,
  Check,
  ChevronRight,
  CircleAlert,
  Crown,
  Dices,
  Gauge,
  History,
  LoaderCircle,
  LockKeyhole,
  RotateCcw,
  Shield,
  Sparkles,
  Target,
  Trophy,
  Users,
  Waypoints,
} from "lucide-react";
import field from "../../data/wc2026-field.json";
import { FORMATIONS } from "../../lib/formations";
import { mapPlayerAverageToTeamStrength } from "../../lib/simulation";
import type { ClassicRatingMode, DraftPlayer, FieldTeam, FormationName, HistoricSquad, SimMatch } from "../../lib/types";
import { useGameStore } from "../../store/game-store";
import { MossCredentialsProvider } from "../scout/moss-credentials-context";
import { EraDraftPhase, EraSpinPhase } from "./era-phases";
import { Pitch } from "./pitch";
import { ScoutPhase } from "./scout-phase";
import { SquadDnaPhase } from "./squad-dna-phase";

const formationCopy: Record<FormationName, { label: string; note: string }> = {
  "4-3-3": { label: "Front-foot", note: "+3 attack" },
  "4-4-2": { label: "Balanced", note: "+2 defense" },
  "3-5-2": { label: "Overload", note: "+2 attack" },
};

function formatScore(match: SimMatch) {
  let score = `${match.homeGoals}–${match.awayGoals}`;
  if (match.penalties) score += ` (${match.penalties.home}–${match.penalties.away} pens)`;
  else if (match.afterExtraTime) score += " AET";
  return score;
}

function ModePhase() {
  const chooseMode = useGameStore((state) => state.chooseMode);
  return (
    <section className="mode-phase">
      <div className="mode-heading"><span className="step-tag">Choose a game mode</span><h1>How will you<br />build history?</h1><p>Both roads end with Squad DNA and a complete 2026 World Cup simulation.</p></div>
      <div className="mode-cards">
        <button type="button" className="mode-card classic-mode-card" onClick={() => chooseMode("classic")}>
          <span className="mode-number">01</span><div className="mode-icon"><Dices size={26} /></div><span className="eyebrow">The original</span><h2>Classic Wheel</h2><p>Spin 11 different historical squads. Choose exact World Cup form or career-prime ratings, then take one eligible player from each roll.</p><div className="mode-tags"><span>11 squad spins</span><span>Two rating rules</span><span>One Moss swap</span></div><strong>Play Classic <ArrowRight size={18} /></strong>
        </button>
        <button type="button" className="mode-card era-mode-card" onClick={() => chooseMode("era")}>
          <span className="mode-number">02</span><div className="mode-icon"><History size={26} /></div><span className="eyebrow">New mode</span><h2>World Cup Era</h2><p>Spin a World Cup year for each of your 11 picks. Browse that tournament’s complete roster, choose one player, then spin a new year.</p><div className="mode-tags"><span>11 era spins</span><span>One pick per year</span><span>Year-scoped Moss</span></div><strong>Play World Cup Era <ArrowRight size={18} /></strong>
        </button>
      </div>
    </section>
  );
}

function SetupPhase() {
  const gameMode = useGameStore((state) => state.gameMode);
  const formation = useGameStore((state) => state.formation);
  const setFormation = useGameStore((state) => state.setFormation);
  const beginDraft = useGameStore((state) => state.beginDraft);
  const backToModes = useGameStore((state) => state.backToModes);
  return (
    <section className="game-phase setup-phase">
      <div className="phase-copy">
        <span className="step-tag">01 / {gameMode === "era" ? "World Cup Era" : "Classic Wheel"}</span>
        <h1>Choose your system.</h1>
        <p>Your formation fixes the positions you need to fill and adds a small tactical modifier in the match engine. {gameMode === "era" ? "Next, spin a separate World Cup year for each player you draft." : "Next, choose World Cup Form or Prime Form before the original squad wheel begins."}</p>
        <div className="formation-options">
          {(Object.keys(FORMATIONS) as FormationName[]).map((name) => (
            <button key={name} type="button" className={`formation-card ${formation === name ? "selected" : ""}`} onClick={() => setFormation(name)}>
              <span><Shield size={18} /> {formationCopy[name].label}</span>
              <strong>{name}</strong>
              <small>{formationCopy[name].note}</small>
              {formation === name && <i><Check size={13} /></i>}
            </button>
          ))}
        </div>
        <button type="button" className="button button-primary button-large" onClick={beginDraft}>Lock formation <ArrowRight size={18} /></button>
        <button type="button" className="text-button setup-back" onClick={backToModes}>Back to game modes</button>
      </div>
      <div className="setup-pitch-wrap">
        <Pitch formation={formation} picks={[]} />
        <div className="pitch-caption"><span>{formation}</span><small>11 open positions</small></div>
      </div>
    </section>
  );
}

function ClassicRatingPhase() {
  const formation = useGameStore((state) => state.formation);
  const chooseClassicRatingMode = useGameStore((state) => state.chooseClassicRatingMode);
  const reset = useGameStore((state) => state.reset);
  const choices: Array<{ mode: ClassicRatingMode; icon: typeof History; eyebrow: string; title: string; rating: string; example: string; copy: string }> = [
    {
      mode: "campaign",
      icon: History,
      eyebrow: "Original rules",
      title: "World Cup Form",
      rating: "2010 MESSI · 77",
      example: "Every tournament version is different",
      copy: "Ratings reflect only how the player performed in the exact World Cup squad you spun—appearances, goals and team finish included.",
    },
    {
      mode: "prime",
      icon: Crown,
      eyebrow: "Career peak",
      title: "Prime Form",
      rating: "ANY MESSI · 94",
      example: "One peak rating across every version",
      copy: "Keep the real rolled roster, but rate each selectable player at his estimated absolute career prime, regardless of that tournament’s form.",
    },
  ];
  return (
    <section className="classic-rating-phase">
      <div className="rating-mode-heading"><span className="step-tag">02 / Choose the rating lens</span><h1>Which version<br />of history?</h1><p>Your {formation} stays locked. This choice changes player ratings throughout the Classic draft, Moss transfer, Squad DNA and simulation.</p></div>
      <div className="rating-mode-options">
        {choices.map(({ mode, icon: Icon, eyebrow, title, rating, example, copy }) => (
          <button type="button" className={`rating-mode-card ${mode}`} key={mode} onClick={() => chooseClassicRatingMode(mode)}>
            <div className="rating-mode-icon"><Icon size={25} /></div><span className="eyebrow">{eyebrow}</span><h2>{title}</h2><p>{copy}</p><div className="rating-example"><strong>{rating}</strong><small>{example}</small></div><b>Use {title} <ArrowRight size={17} /></b>
          </button>
        ))}
      </div>
      <button type="button" className="text-button" onClick={reset}>Back to formation</button>
    </section>
  );
}

function DraftPhase() {
  const classicRatingMode = useGameStore((state) => state.classicRatingMode);
  const formation = useGameStore((state) => state.formation);
  const picks = useGameStore((state) => state.picks);
  const currentSquad = useGameStore((state) => state.currentSquad);
  const usedSquads = useGameStore((state) => state.usedSquads);
  const setCurrentSquad = useGameStore((state) => state.setCurrentSquad);
  const assignPlayer = useGameStore((state) => state.assignPlayer);
  const removePick = useGameStore((state) => state.removePick);
  const reset = useGameStore((state) => state.reset);
  const [selectedPlayer, setSelectedPlayer] = useState<DraftPlayer | null>(null);
  const [spinning, setSpinning] = useState(false);
  const [error, setError] = useState("");

  const openPositions = useMemo(() => {
    const filled = new Set(picks.map((pick) => pick.slotId));
    return FORMATIONS[formation].filter((slot) => !filled.has(slot.id)).map((slot) => slot.position);
  }, [formation, picks]);
  const eligiblePlayers = currentSquad?.players.filter((player) => openPositions.includes(player.position)) ?? [];

  async function spin() {
    setSpinning(true);
    setSelectedPlayer(null);
    setError("");
    try {
      const request = fetch(`/api/squads?used=${encodeURIComponent(usedSquads.join(","))}&ratingMode=${classicRatingMode}`).then(async (response) => {
        if (!response.ok) throw new Error("The wheel could not find another squad.");
        return response.json() as Promise<HistoricSquad>;
      });
      const [squad] = await Promise.all([request, new Promise((resolve) => setTimeout(resolve, 1250))]);
      setCurrentSquad(squad);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Spin failed.");
    } finally {
      setSpinning(false);
    }
  }

  function assign(slotId: string) {
    if (!selectedPlayer) return;
    assignPlayer(selectedPlayer, slotId);
    setSelectedPlayer(null);
  }

  return (
    <section className="draft-layout">
      <aside className="draft-sidebar">
        <div className="draft-progress-head">
          <div><span className="step-tag">03 / {classicRatingMode === "prime" ? "Prime draft" : "World Cup form"}</span><h1>{picks.length}<small>/11</small></h1></div>
          <button type="button" className="icon-button" onClick={reset} aria-label="Restart draft"><RotateCcw size={16} /></button>
        </div>
        <div className="progress-track"><span style={{ width: `${(picks.length / 11) * 100}%` }} /></div>
        <p>{selectedPlayer ? `Choose a glowing ${selectedPlayer.position} slot for ${selectedPlayer.name}.` : currentSquad ? "Pick one eligible player from this World Cup squad." : "Spin for a historic nation and year."}</p>
        <div className="mini-draft-list">
          {FORMATIONS[formation].map((slot) => {
            const pick = picks.find((item) => item.slotId === slot.id);
            return <div key={slot.id} className={pick ? "complete" : ""}><span>{slot.label}</span><strong>{pick?.player.name ?? "Open"}</strong>{pick && <small>{pick.player.rating}</small>}</div>;
          })}
        </div>
      </aside>

      <div className="draft-pitch-column">
        <Pitch formation={formation} picks={picks} selectedPlayer={selectedPlayer} onAssign={assign} onRemove={selectedPlayer ? undefined : removePick} />
        <div className="selection-hint">
          {selectedPlayer ? <><Sparkles size={15} /> Select a highlighted slot to confirm</> : <><Target size={15} /> {11 - picks.length} positions left</>}
        </div>
      </div>

      <div className="draft-pool-panel">
        {!currentSquad ? (
          <div className="wheel-stage">
            <div className={`wheel ${spinning ? "spinning" : ""}`}>
              <div className="wheel-ring" />
              <div className="wheel-core"><span>{spinning ? "?" : picks.length + 1}</span><small>{spinning ? "SEARCHING" : "NEXT PICK"}</small></div>
              <i className="wheel-pointer" />
            </div>
            <h2>{spinning ? "History is turning…" : "Spin the World Cup wheel"}</h2>
            <p>489 real squads. {classicRatingMode === "prime" ? "Every player appears at his estimated career-prime rating." : "Every rating belongs to that specific World Cup campaign."}</p>
            {error && <div className="inline-error"><CircleAlert size={15} /> {error}</div>}
            <button type="button" className="button button-primary button-large" onClick={spin} disabled={spinning}>
              {spinning ? <LoaderCircle className="spin-icon" size={18} /> : <Dices size={18} />} {spinning ? "Spinning" : "Spin the wheel"}
            </button>
          </div>
        ) : (
          <div className="squad-panel">
            <div className="squad-title-row">
              <div className="nation-stamp"><span>{currentSquad.nationCode}</span></div>
              <div><span className="eyebrow">The wheel says</span><h2>{currentSquad.nation} <b>{currentSquad.year}</b></h2><p>{currentSquad.finish} · {currentSquad.players.length}-player squad</p></div>
            </div>
            <div className="roster-guide"><span>Select one player</span><small>{eligiblePlayers.length} fit your open slots</small></div>
            <div className="player-grid">
              {eligiblePlayers.map((player) => (
                <button key={player.id} type="button" className={`player-card ${selectedPlayer?.id === player.id ? "selected" : ""}`} onClick={() => setSelectedPlayer(selectedPlayer?.id === player.id ? null : player)}>
                  <div className="player-rating"><strong>{player.rating}</strong><span>{player.subPosition}</span></div>
                  <div className="player-card-copy"><strong>{player.name}</strong><small>{player.ratingMode === "prime" ? `Prime rating · ${player.year} form ${player.campaignRating}` : `${player.inputs.appearances} apps · ${player.inputs.goals} goals`}</small></div>
                  <span className="card-chevron"><ChevronRight size={15} /></span>
                </button>
              ))}
            </div>
            {!eligiblePlayers.length && <div className="inline-error"><CircleAlert size={15} /> No player in this roster fits your remaining slots. This squad is skipped automatically.</div>}
          </div>
        )}
      </div>
    </section>
  );
}

function EntryPhase() {
  const gameMode = useGameStore((state) => state.gameMode);
  const classicRatingMode = useGameStore((state) => state.classicRatingMode);
  const eraYear = useGameStore((state) => state.eraYear);
  const usedEraYears = useGameStore((state) => state.usedEraYears);
  const formation = useGameStore((state) => state.formation);
  const picks = useGameStore((state) => state.picks);
  const scoutReplacement = useGameStore((state) => state.scoutReplacement);
  const squadDna = useGameStore((state) => state.squadDna);
  const openScout = useGameStore((state) => state.openScout);
  const beginSimulation = useGameStore((state) => state.beginSimulation);
  const setResult = useGameStore((state) => state.setResult);
  const returnToEntry = useGameStore((state) => state.returnToEntry);
  const [selectedTeam, setSelectedTeam] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const groups = useMemo(() => Object.groupBy(field as FieldTeam[], (team) => team.group), []);
  const selected = (field as FieldTeam[]).find((team) => team.team === selectedTeam);
  const rating = Math.round(picks.reduce((sum, pick) => sum + pick.player.rating, 0) / 11);
  const simulationStrength = mapPlayerAverageToTeamStrength(rating);

  async function simulate() {
    if (!selectedTeam) return;
    setLoading(true);
    setError("");
    beginSimulation();
    try {
      const response = await fetch("/api/simulate", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ xi: picks, formation, replacedTeam: selectedTeam, gameMode, classicRatingMode, eraYear, eraYears: usedEraYears, squadDna }),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body.error ?? "Simulation failed.");
      setResult(body);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Simulation failed.");
      returnToEntry();
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="entry-layout">
      <div className="entry-copy">
        <span className="step-tag">{gameMode === "classic" ? "06" : "05"} / Enter the bracket</span>
        <h1>Take someone’s place.</h1>
        <p>Choose one real 2026 nation. Your XI inherits its group, opponents and route through the tournament.</p>
        {gameMode === "classic" && <div className="rating-rules-chip"><Crown size={15} /><span>Classic ratings</span><strong>{classicRatingMode === "prime" ? "Prime Form" : "World Cup Form"}</strong></div>}
        {gameMode === "classic" && scoutReplacement ? (
          <div className="completed-scout-transfer">
            <Sparkles size={17} />
            <div><span>Moss transfer complete</span><strong>{scoutReplacement.outgoing.name} → {scoutReplacement.incoming.name}</strong></div>
          </div>
        ) : gameMode === "classic" ? (
          <button type="button" className="reopen-scout-button" onClick={openScout}><Sparkles size={16} /><span><strong>Want your Moss transfer?</strong><small>You can still replace one position-compatible player before entering.</small></span><ArrowRight size={16} /></button>
        ) : <div className="completed-scout-transfer"><History size={17} /><div><span>World Cup Era squad</span><strong>11 players from {usedEraYears.length} tournament years</strong></div></div>}
        {squadDna && <div className="entry-dna-chip"><Waypoints size={16} /><span>Squad DNA</span><strong>{squadDna.match.nation} {squadDna.match.year}</strong><small>{squadDna.similarity}% match</small></div>}
        <label className="field-label" htmlFor="team-slot">World Cup 2026 slot</label>
        <select id="team-slot" className="team-select" value={selectedTeam} onChange={(event) => setSelectedTeam(event.target.value)}>
          <option value="">Select a nation…</option>
          {Object.entries(groups).map(([group, teams]) => (
            <optgroup label={`Group ${group}`} key={group}>{teams?.map((team) => <option value={team.team} key={team.team}>{team.team} · FIFA #{team.fifaRanking}</option>)}</optgroup>
          ))}
        </select>
        {selected && (
          <div className="selected-group-card">
            <div><span>GROUP {selected.group}</span><strong>{selected.team}</strong><small>FIFA #{selected.fifaRanking} · {selected.strengthRating} strength</small></div>
            <div className="group-opponents">
              {(field as FieldTeam[]).filter((team) => team.group === selected.group && team.team !== selected.team).map((team) => <span key={team.team}>{team.team}</span>)}
            </div>
          </div>
        )}
        {error && <div className="inline-error"><CircleAlert size={15} /> {error}</div>}
        <button type="button" className="button button-primary button-large" onClick={simulate} disabled={!selectedTeam || loading}>
          {loading ? <LoaderCircle className="spin-icon" size={18} /> : <Trophy size={18} />} {loading ? "Building tournament" : "Enter World Cup"}
        </button>
      </div>
      <div className="entry-xi-card">
        <div className="entry-xi-head"><div><span className="eyebrow">Your final XI</span><h2>{formation}</h2></div><div className="rating-orb"><strong>{rating}</strong><small>OVR</small></div></div>
        <Pitch formation={formation} picks={picks} compact />
        <div className="entry-metrics"><span><Gauge size={15} /> {rating} player avg → {simulationStrength} sim strength</span><span><Users size={15} /> {new Set(picks.map((pick) => pick.player.nation)).size} nations</span></div>
      </div>
    </section>
  );
}

function SimulationPhase() {
  const router = useRouter();
  const result = useGameStore((state) => state.result);
  const gameMode = useGameStore((state) => state.gameMode);
  const [revealCount, setRevealCount] = useState(0);
  if (!result) {
    return <section className="simulation-loading"><span className="loader-ring" /><span className="step-tag">{gameMode === "classic" ? "07" : "06"} / Simulation</span><h1>Drawing the tournament…</h1><p>Simulating the complete World Cup around your custom XI.</p></section>;
  }
  const visible = result.path.slice(0, revealCount);
  const groupDone = revealCount >= Math.min(3, result.path.length);
  const complete = revealCount >= result.path.length;
  const next = result.path[revealCount];
  return (
    <section className="simulation-layout">
      <div className="simulation-head"><div><span className="step-tag">{gameMode === "classic" ? "07" : "06"} / Simulation</span><h1>The road to {result.perfect ? "8–0" : "glory"}.</h1></div><div className="live-badge"><span /> TOURNAMENT ENGINE</div></div>
      <div className="simulation-grid">
        <div className="sim-timeline">
          {visible.map((match, index) => (
            <article key={match.id} className={`sim-match outcome-${match.customOutcome?.toLowerCase()}`}>
              <div className="sim-index">{String(index + 1).padStart(2, "0")}</div>
              <div><span>{match.stage}</span><strong>{match.home} <b>{formatScore(match)}</b> {match.away}</strong><small>{match.penalties ? "Decided on penalties" : match.afterExtraTime ? "After extra time" : "Full time"}</small></div>
              <div className="sim-outcome">{match.customOutcome}</div>
            </article>
          ))}
          {!visible.length && <div className="sim-empty"><LockKeyhole size={30} /><h3>The fixtures are sealed.</h3><p>Reveal your group stage to begin.</p></div>}
          {!complete && visible.length > 0 && <div className="next-fixture"><span>UP NEXT</span><strong>{next?.stage}</strong><small>Champions XI vs {next?.customOpponent}</small></div>}
        </div>
        <aside className="sim-side-panel">
          <span className="eyebrow">Group {result.group}</span><h3>{groupDone ? "Final standings" : "Table pending"}</h3>
          {groupDone ? (
            <table className="group-table"><thead><tr><th>#</th><th>Team</th><th>GD</th><th>Pts</th></tr></thead><tbody>{result.groupTable.map((row, index) => <tr key={row.team} className={row.team === "Champions XI" ? "custom-row" : ""}><td>{index + 1}</td><td>{row.team}</td><td>{row.gd > 0 ? `+${row.gd}` : row.gd}</td><td><strong>{row.points}</strong></td></tr>)}</tbody></table>
          ) : <div className="table-skeleton">{[1, 2, 3, 4].map((row) => <span key={row} />)}</div>}
          <div className="sim-record"><span>{result.record.wins}</span><small>W</small><span>{result.record.draws}</span><small>D</small><span>{result.record.losses}</span><small>L</small></div>
        </aside>
      </div>
      <div className="simulation-actions">
        {!complete ? (
          <button type="button" className="button button-primary button-large" onClick={() => setRevealCount(revealCount === 0 ? Math.min(3, result.path.length) : revealCount + 1)}>
            {revealCount === 0 ? "Simulate group stage" : `Play ${next?.stage}`} <ArrowRight size={18} />
          </button>
        ) : (
          <button type="button" className="button button-primary button-large" onClick={() => router.push(`/results/${result.id}`)}>
            View final result <Trophy size={18} />
          </button>
        )}
      </div>
    </section>
  );
}

export function GameClient() {
  const phase = useGameStore((state) => state.phase);
  return (
    <MossCredentialsProvider>
      <main className="game-main shell-wide">
        {phase === "mode" && <ModePhase />}
        {phase === "setup" && <SetupPhase />}
        {phase === "classic-ratings" && <ClassicRatingPhase />}
        {phase === "draft" && <DraftPhase />}
        {phase === "era-spin" && <EraSpinPhase />}
        {phase === "era-draft" && <EraDraftPhase />}
        {phase === "scout" && <ScoutPhase />}
        {phase === "dna" && <SquadDnaPhase />}
        {phase === "entry" && <EntryPhase />}
        {phase === "simulation" && <SimulationPhase />}
      </main>
    </MossCredentialsProvider>
  );
}
