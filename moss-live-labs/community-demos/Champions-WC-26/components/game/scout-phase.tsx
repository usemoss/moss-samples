"use client";

import { useMemo, useState } from "react";
import { ArrowRight, Check, ShieldCheck, Sparkles } from "lucide-react";
import type { DraftPlayer } from "../../lib/types";
import { useGameStore } from "../../store/game-store";
import { MossSearchPanel } from "../scout/moss-search-panel";
import { Pitch } from "./pitch";

export function ScoutPhase() {
  const formation = useGameStore((state) => state.formation);
  const classicRatingMode = useGameStore((state) => state.classicRatingMode);
  const picks = useGameStore((state) => state.picks);
  const skipScout = useGameStore((state) => state.skipScout);
  const applyScoutReplacement = useGameStore((state) => state.applyScoutReplacement);
  const [candidate, setCandidate] = useState<DraftPlayer | null>(null);
  const [outgoingSlot, setOutgoingSlot] = useState("");
  const compatiblePicks = useMemo(() => candidate ? picks.filter((pick) => pick.player.position === candidate.position) : [], [candidate, picks]);

  function chooseCandidate(player: DraftPlayer) {
    setCandidate(player);
    setOutgoingSlot("");
  }

  function confirmTransfer() {
    if (!candidate || !outgoingSlot) return;
    applyScoutReplacement(candidate, outgoingSlot);
  }

  return (
    <section className="scout-transfer-layout">
      <aside className="scout-transfer-xi">
        <div className="scout-transfer-heading">
          <span className="step-tag">04 / Moss Scout</span>
          <h1>One move.<br />Anyone.</h1>
          <p>Your eleven spins are complete. Moss gives you one optional, position-compatible replacement from the entire World Cup archive. {classicRatingMode === "prime" ? "Every result uses its career-prime rating." : "Ratings remain campaign-specific."}</p>
        </div>
        <div className="scout-pitch-card">
          <div className="scout-pitch-head"><span>Your drafted XI</span><strong>{formation}</strong></div>
          <Pitch formation={formation} picks={picks} compact />
        </div>
        <button type="button" className="button button-ghost scout-skip" onClick={skipScout}>Skip Scout and keep this XI <ArrowRight size={16} /></button>
      </aside>
      <div className="scout-transfer-workspace">
        {candidate && (
          <section className="transfer-confirm-panel">
            <div className="transfer-incoming">
              <span><Sparkles size={14} /> Incoming</span>
              <strong>{candidate.name}</strong>
              <small>{candidate.nation} {candidate.year} · {candidate.subPosition} · {candidate.rating} {candidate.ratingMode === "prime" ? `PRIME (${candidate.campaignRating} WC form)` : "OVR"}</small>
            </div>
            <div className="transfer-arrow"><ArrowRight size={20} /></div>
            <div className="transfer-outgoing">
              <span>Choose the {candidate.position} leaving your XI</span>
              <div>{compatiblePicks.map((pick) => (
                <button type="button" key={pick.slotId} className={outgoingSlot === pick.slotId ? "selected" : ""} onClick={() => setOutgoingSlot(pick.slotId)}>
                  <i>{pick.player.rating}</i><strong>{pick.player.name}</strong><small>{pick.player.nationCode} {pick.player.year}</small>{outgoingSlot === pick.slotId && <Check size={13} />}
                </button>
              ))}</div>
            </div>
            <button type="button" className="button button-primary" onClick={confirmTransfer} disabled={!outgoingSlot}><ShieldCheck size={17} /> Confirm one-time swap</button>
          </section>
        )}
        <MossSearchPanel
          compactIntro
          ratingMode={classicRatingMode}
          onChoose={chooseCandidate}
          selectedPlayerId={candidate?.id}
          excludedPlayerIds={picks.map((pick) => pick.player.id)}
          actionLabel="Bring into XI"
        />
      </div>
    </section>
  );
}
