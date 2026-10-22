import Link from "next/link";
import { ArrowUpRight } from "lucide-react";

export function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <Link href="/" className="brand" aria-label="Champions WC 26 home">
      <span className="brand-ball" aria-hidden="true"><span /></span>
      <span className="brand-copy">
        <strong>CHAMPIONS</strong>
        {!compact && <small>WC 26</small>}
      </span>
    </Link>
  );
}

export function SiteHeader() {
  return (
    <header className="site-header">
      <div className="shell header-inner">
        <Brand />
        <nav aria-label="Primary navigation">
          <Link href="/how-to-play">How to play</Link>
          <Link href="/scout">Moss Scout Lab</Link>
          <Link href="/game" className="nav-cta">Build your XI <ArrowUpRight size={14} /></Link>
        </nav>
      </div>
    </header>
  );
}

export function SiteFooter() {
  return (
    <footer className="site-footer">
      <div className="shell footer-grid">
        <Brand />
        <p>
          An unofficial fan-made project. Not affiliated with or endorsed by FIFA or any confederation.
          Ratings are an independent interpretation of public historical data.
        </p>
        <div className="footer-links">
          <Link href="/disclaimer">Disclaimer</Link>
          <Link href="/how-to-play">How to play</Link>
          <Link href="/scout">Moss Scout Lab</Link>
          <a href="https://github.com/jfjelstul/worldcup" target="_blank" rel="noreferrer">Data source</a>
        </div>
      </div>
    </footer>
  );
}
