"use client";

import { Plus, X } from "lucide-react";
import { FORMATIONS } from "../../lib/formations";
import type { DraftPick, DraftPlayer, FormationName } from "../../lib/types";

type PitchProps = {
  formation: FormationName;
  picks: DraftPick[];
  selectedPlayer?: DraftPlayer | null;
  onAssign?: (slotId: string) => void;
  onRemove?: (slotId: string) => void;
  compact?: boolean;
};

export function Pitch({ formation, picks, selectedPlayer, onAssign, onRemove, compact = false }: PitchProps) {
  const slots = FORMATIONS[formation];
  return (
    <div className={`pitch ${compact ? "pitch-compact" : ""}`} aria-label={`${formation} formation`}>
      <div className="pitch-half" />
      <div className="pitch-circle" />
      <div className="pitch-box pitch-box-top" />
      <div className="pitch-box pitch-box-bottom" />
      {slots.map((slot) => {
        const pick = picks.find((item) => item.slotId === slot.id);
        const compatible = selectedPlayer?.position === slot.position && !pick;
        return (
          <button
            key={slot.id}
            type="button"
            className={`pitch-slot ${pick ? "filled" : ""} ${compatible ? "compatible" : ""}`}
            style={{ left: `${slot.x}%`, top: `${slot.y}%` }}
            onClick={() => compatible ? onAssign?.(slot.id) : pick ? onRemove?.(slot.id) : undefined}
            disabled={!compatible && !pick}
            aria-label={pick ? `${pick.player.name}, ${slot.label}` : `Empty ${slot.label} slot`}
          >
            {pick ? (
              <>
                {onRemove && <span className="remove-pick"><X size={10} /></span>}
                <span className="slot-rating">{pick.player.rating}</span>
                <strong>{pick.player.name.split(" ").at(-1)}</strong>
                <small>{pick.player.nationCode} · {pick.player.ratingMode === "prime" ? `PRIME · ${pick.player.year}` : pick.player.year}</small>
              </>
            ) : (
              <>
                <span className="slot-plus"><Plus size={14} /></span>
                <strong>{slot.label}</strong>
              </>
            )}
          </button>
        );
      })}
    </div>
  );
}
