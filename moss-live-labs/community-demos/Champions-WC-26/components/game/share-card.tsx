"use client";

import { useRef, useState } from "react";
import { Download, Share2 } from "lucide-react";
import type { TournamentResult } from "../../lib/types";

export function ShareCard({ result }: { result: TournamentResult }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [ready, setReady] = useState(false);

  function draw() {
    const canvas = canvasRef.current;
    if (!canvas) return;
    canvas.width = 1200;
    canvas.height = 630;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const gradient = ctx.createLinearGradient(0, 0, 1200, 630);
    gradient.addColorStop(0, "#07111f");
    gradient.addColorStop(1, "#10293a");
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, 1200, 630);
    ctx.fillStyle = "#c8ff38";
    ctx.fillRect(58, 58, 14, 514);
    ctx.font = "700 38px Arial";
    ctx.fillText("CHAMPIONS (WC 26)", 112, 118);
    ctx.fillStyle = "#9db0b8";
    ctx.font = "700 20px Arial";
    ctx.fillText(result.gameMode === "era" ? `WORLD CUP ERA · ${result.eraYears?.length ?? 11} YEAR SPINS` : `CLASSIC · ${result.classicRatingMode === "prime" ? "PRIME FORM" : "WORLD CUP FORM"}`, 760, 112);
    ctx.fillStyle = "#f3f7f5";
    ctx.font = "900 156px Arial";
    const record = result.perfect ? "8–0" : `${result.record.wins}–${result.record.draws}–${result.record.losses}`;
    ctx.fillText(record, 105, 310);
    ctx.fillStyle = result.champion ? "#c8ff38" : "#9db0b8";
    ctx.font = "800 52px Arial";
    ctx.fillText(result.champion ? "WORLD CHAMPIONS" : result.reached.toUpperCase(), 112, 390);
    ctx.fillStyle = "#9db0b8";
    ctx.font = "500 28px Arial";
    ctx.fillText(`${result.formation}  ·  ${result.squadRating} SIM STRENGTH  ·  ${result.goalsFor} GF / ${result.goalsAgainst} GA`, 112, 458);
    ctx.fillStyle = "#ffffff";
    ctx.font = "600 24px Arial";
    ctx.fillText(`Replaced ${result.replacedTeam} in Group ${result.group}`, 112, 516);
    if (result.squadDna) {
      ctx.fillStyle = "#9db0b8";
      ctx.font = "600 20px Arial";
      ctx.fillText(`SQUAD DNA: ${result.squadDna.match.nation.toUpperCase()} ${result.squadDna.match.year} · ${result.squadDna.similarity}%`, 112, 558);
    }
    ctx.fillStyle = "#c8ff38";
    ctx.font = "800 24px Arial";
    ctx.fillText("CAN YOU GO 8–0?", 858, 594);
    setReady(true);
  }

  async function share() {
    draw();
    const canvas = canvasRef.current;
    if (!canvas) return;
    canvas.toBlob(async (blob) => {
      if (!blob) return;
      const file = new File([blob], `champions-${result.id ?? "run"}.png`, { type: "image/png" });
      if (navigator.canShare?.({ files: [file] })) {
        await navigator.share({ title: "Champions (WC 26)", text: `My World Cup run: ${result.record.wins}-${result.record.draws}-${result.record.losses}`, files: [file] });
      } else {
        const link = document.createElement("a");
        link.download = file.name;
        link.href = URL.createObjectURL(blob);
        link.click();
        URL.revokeObjectURL(link.href);
      }
    });
  }

  return (
    <div className="share-card-panel">
      <div>
        <span className="eyebrow">Share the run</span>
        <h3>Put your record on the timeline.</h3>
        <p>Your XI, record and World Cup finish in one clean card.</p>
      </div>
      <canvas ref={canvasRef} className={ready ? "share-canvas visible" : "share-canvas"} aria-label="Generated Champions WC 26 share card" />
      <button type="button" className="button button-light" onClick={share}>
        {ready ? <Download size={17} /> : <Share2 size={17} />} {ready ? "Save or share" : "Generate card"}
      </button>
    </div>
  );
}
