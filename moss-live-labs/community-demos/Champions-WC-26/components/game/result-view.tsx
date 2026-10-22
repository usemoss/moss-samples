"use client";

import Link from "next/link";
import { ArrowLeft, Check, Crown, Dna, RotateCcw, ShieldCheck, Sparkles, Trophy } from "lucide-react";
import type { TournamentResult } from "../../lib/types";
import { Pitch } from "./pitch";
import { ShareCard } from "./share-card";

function scoreFor(match: TournamentResult["path"][number]) {
  const base = `${match.homeGoals}–${match.awayGoals}`;
  if (match.penalties) return `${base} (${match.penalties.home}–${match.penalties.away} pens)`;
  if (match.afterExtraTime) return `${base} AET`;
  return base;
}

export function ResultView({ result, onReset }: { result: TournamentResult; onReset?: () => void }) {
  const record = `${result.record.wins}–${result.record.draws}–${result.record.losses}`;
  return (
    <main className="results-main">
      <section className={`result-hero ${result.champion ? "champion" : ""}`}>
        <div className="result-glow" />
        <div className="shell result-hero-inner">
          <Link href="/game" className="back-link"><ArrowLeft size={16} /> Back to draft room</Link>
          <div className="result-kicker">
            {result.champion ? <Crown size={18} /> : <ShieldCheck size={18} />}
            {result.champion ? "WORLD CHAMPIONS" : "TOURNAMENT COMPLETE"}
          </div>
          <div className="result-ruleset">{result.gameMode === "era" ? "WORLD CUP ERA" : `CLASSIC · ${result.classicRatingMode === "prime" ? "PRIME FORM" : "WORLD CUP FORM"}`}</div>
          <div className="record-lockup">
            <span className="record-value">{result.perfect ? "8–0" : record}</span>
            <span className="record-caption">{result.perfect ? "THE PERFECT RUN" : result.reached.toUpperCase()}</span>
          </div>
          <p className="result-lede">
            {result.perfect
              ? "Eleven icons. Eight wins. No penalties needed. You built the impossible World Cup run."
              : result.champion
                ? "Your all-time XI survived the bracket and lifted the trophy. The 8–0 remains the next mountain."
                : `Your run ended at the ${result.reached.toLowerCase()}, but this XI left a trail through Group ${result.group}.`}
          </p>
          <div className="result-stats">
            <div><span>{result.goalsFor}</span><small>Goals for</small></div>
            <div><span>{result.goalsAgainst}</span><small>Goals against</small></div>
            <div><span>{result.squadRating}</span><small>Sim strength{result.playerAverageRating ? ` · ${result.playerAverageRating} avg` : ""}</small></div>
            <div><span>{result.formation}</span><small>Formation</small></div>
          </div>
        </div>
      </section>

      <section className="shell result-content">
        <div className="result-section-heading">
          <div><span className="eyebrow">The road</span><h2>Eight games or bust.</h2></div>
          {result.perfect && <span className="perfect-pill"><Sparkles size={15} /> Perfect 8–0</span>}
        </div>
        <div className="path-grid">
          {result.path.map((match, index) => (
            <article className={`path-card outcome-${match.customOutcome?.toLowerCase()}`} key={match.id}>
              <div className="path-card-top"><span>{index + 1}</span><small>{match.stage}</small></div>
              <div className="path-score-row">
                <strong>{match.home}</strong>
                <b>{scoreFor(match)}</b>
                <strong>{match.away}</strong>
              </div>
              <div className="path-card-foot">
                {match.customOutcome === "W" ? <Check size={14} /> : null}
                {match.penalties ? "Decided on penalties" : match.afterExtraTime ? "After extra time" : "Full time"}
              </div>
            </article>
          ))}
          {Array.from({ length: Math.max(0, 8 - result.path.length) }).map((_, index) => (
            <article className="path-card path-empty" key={`empty-${index}`}>
              <div className="path-card-top"><span>{result.path.length + index + 1}</span><small>Not reached</small></div>
              <div className="empty-line" />
            </article>
          ))}
        </div>

        <div className="result-two-col">
          <section className="panel result-panel">
            <span className="eyebrow">Group {result.group}</span>
            <h3>Final table</h3>
            <div className="table-wrap">
              <table className="group-table">
                <thead><tr><th>#</th><th>Team</th><th>P</th><th>GD</th><th>Pts</th></tr></thead>
                <tbody>
                  {result.groupTable.map((row, index) => (
                    <tr key={row.team} className={row.team === "Champions XI" ? "custom-row" : ""}>
                      <td>{index + 1}</td><td>{row.team}</td><td>{row.played}</td><td>{row.gd > 0 ? `+${row.gd}` : row.gd}</td><td><strong>{row.points}</strong></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
          <section className="panel result-panel xi-panel">
            <div className="xi-panel-head"><div><span className="eyebrow">Your XI</span><h3>{result.formation}</h3></div><Trophy size={26} /></div>
            <Pitch formation={result.formation} picks={result.xi} compact />
          </section>
        </div>

        {result.squadDna && (
          <section className="result-dna-banner">
            <Dna size={28} />
            <div><span className="eyebrow">Your Squad DNA</span><h3>{result.squadDna.match.nation} {result.squadDna.match.year}</h3><p>{result.squadDna.explanation}</p></div>
            <strong>{result.squadDna.similarity}%<small>match</small></strong>
          </section>
        )}

        <ShareCard result={result} />

        <div className="result-actions">
          <Link href="/game" className="button button-primary" onClick={onReset}><RotateCcw size={17} /> Draft another XI</Link>
          <Link href="/" className="button button-ghost">Back to home</Link>
        </div>
      </section>
    </main>
  );
}
