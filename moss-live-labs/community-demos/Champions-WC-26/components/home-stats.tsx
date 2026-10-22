"use client";

import { useEffect, useState } from "react";

export function HomeStats() {
  const [stats, setStats] = useState({ runs: 0, champions: 0, perfectRuns: 0 });
  useEffect(() => { fetch("/api/stats").then((response) => response.json()).then(setStats).catch(() => undefined); }, []);
  return (
    <section className="stats-band"><div className="shell stats-grid">
      <div><strong>{stats.runs}</strong><span>Local runs played</span></div>
      <div><strong>{stats.champions}</strong><span>World Cups won</span></div>
      <div><strong>{stats.perfectRuns}</strong><span>Perfect 8–0s</span></div>
      <div><strong>489</strong><span>Squads on the wheel</span></div>
    </div></section>
  );
}
