export const metadata = { title: "Disclaimer & data" };

export default function DisclaimerPage() {
  return <main className="info-page"><section className="info-hero shell"><span className="eyebrow">Transparency</span><h1>Unofficial.<br />Auditable.</h1><p>Champions (WC 26) is an independent fan-made project built for entertainment and football-history exploration.</p></section><section className="shell legal-grid">
    <article><h2>No affiliation</h2><p>This project is not affiliated with, sponsored by, approved by or endorsed by FIFA, any FIFA confederation, national association, player, or rights holder. Tournament, nation and player names are used descriptively.</p></article>
    <article><h2>Historical data</h2><p>Historic squads, appearances, goals and tournament results are derived from The Fjelstul World Cup Database v1.2.0 by Joshua C. Fjelstul, Ph.D. © 2023, published under CC-BY-SA 4.0. This app transforms those records into a game-ready player-tournament pool.</p><a href="https://github.com/jfjelstul/worldcup" target="_blank" rel="noreferrer">View the source database ↗</a></article>
    <article><h2>2026 field</h2><p>The 48-team field and A–L group allocation were checked against the current tournament page and FIFA’s final draw coverage. Team strength uses the official FIFA/Coca-Cola Men’s World Ranking published 11 June 2026.</p></article>
    <article><h2>Independent ratings</h2><p>World Cup Form ratings interpret one tournament campaign. The optional Prime Form ruleset is an editorial career-peak estimate built from curated benchmarks and an archive-wide fallback model. Neither system is an official FIFA or EA Sports rating or a factual measurement. See <code>RATINGS.md</code> in the project for the exact formulas and limitations.</p></article>
    <article><h2>Simulation</h2><p>Match outcomes are fictional. The engine uses seeded Poisson goal sampling, tactical modifiers and close-to-even penalty shootout odds. No result is a prediction or statement about real players or teams.</p></article>
  </section></main>;
}
