import Link from "next/link";
import { ArrowRight, Dices, Dna, History, ListChecks, Search, Trophy } from "lucide-react";

export const metadata = { title: "How to play" };

export default function HowToPlayPage() {
  return <main className="info-page"><section className="info-hero shell"><span className="eyebrow">The rules</span><h1>Two ways<br />to build history.</h1><p>Champions (WC 26) keeps the original squad wheel and adds an eleven-spin World Cup Era mode. Both lead into Squad DNA and the 2026 simulation.</p></section><section className="shell rules-stack">
    {[
      ["01", History, "Choose Classic or World Cup Era", "Classic is the original eleven-squad wheel. World Cup Era spins a tournament year separately for each of your eleven player picks."],
      ["02", Dices, "Choose a formation and rating rules", "Classic then asks for World Cup Form or Prime Form. World Cup Form scores the exact tournament campaign; Prime Form uses one estimated career-peak rating across every version of that player. Era always uses World Cup Form."],
      ["03", Search, "Use Moss in context", "Classic offers one optional position-compatible transfer from all 10,973 campaigns. During each Era pick, search is strictly filtered to that spin’s World Cup roster."],
      ["04", Dna, "Reveal your Squad DNA", "After either XI is complete, Moss compares its attack, defense, goalkeeper, experience and balance with all 489 historical squads to reveal the closest match."],
      ["05", ListChecks, "Replace a 2026 nation", "Choose one of the 48 World Cup 2026 teams. Your custom XI takes that team’s place in its real group."],
      ["06", Trophy, "Survive the tournament", "Play three group matches. Finish in the top two—or as one of the eight best third-placed teams—to reach the Round of 32. Then win five knockout games."],
    ].map(([number, Icon, title, copy]) => <article className="rule-row" key={number as string}><span className="rule-number">{number as string}</span><div className="rule-icon"><Icon size={24} /></div><div><h2>{title as string}</h2><p>{copy as string}</p></div></article>)}
    <div className="perfect-rule"><div><span>THE TARGET</span><strong>8–0</strong></div><p>A perfect run means eight wins and the trophy. Wins after extra time count. A penalty-shootout win advances you, but is visually marked and does not qualify for the perfect badge.</p></div>
    <Link href="/game" className="button button-primary button-large">Start your draft <ArrowRight size={18} /></Link>
  </section></main>;
}
