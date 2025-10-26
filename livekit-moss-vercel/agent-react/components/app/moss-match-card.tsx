import * as React from 'react';
import type { MossContextEvent } from '@/hooks/useMossContextEvents';
import { cn } from '@/lib/utils';

interface MossMatchCardProps extends React.DetailsHTMLAttributes<HTMLDetailsElement> {
  event: MossContextEvent;
}

export function MossMatchCard({ event, className, ...props }: MossMatchCardProps) {
  const { query, matches, timeTakenMs } = event;
  const hasMatches = matches.length > 0;

  return (
    <details
      open
      className={cn(
        'supports-[backdrop-filter]:bg-card/60 group bg-card/80 text-card-foreground border-border/80 border-l-primary/70 shadow-primary/5 rounded-lg border border-l-4 p-3 shadow-sm backdrop-blur',
        className
      )}
      {...props}
    >
      <summary className="flex cursor-pointer items-start gap-3 text-left text-sm leading-tight [&::-webkit-details-marker]:hidden [&::marker]:hidden">
        <span
          aria-hidden
          className="bg-primary/15 text-primary/80 mt-1 flex h-5 w-5 items-center justify-center rounded-full text-xs font-semibold transition-transform duration-200 group-open:rotate-180"
        >
          ▾
        </span>
        <div className="flex-1 space-y-1">
          <span className="text-muted-foreground/80 text-[11px] font-semibold tracking-wide uppercase">
            Knowledge matches
          </span>
          <p className="text-foreground line-clamp-3 text-base leading-snug font-semibold">
            {query}
          </p>
        </div>
        {typeof timeTakenMs === 'number' && (
          <span className="bg-primary/10 text-primary ml-auto rounded-full px-2 py-0.5 text-[11px] font-semibold tracking-wide uppercase">
            {timeTakenMs.toFixed(0)} ms
          </span>
        )}
      </summary>
      <div className="mt-3 space-y-2 text-sm">
        <ol className="text-muted-foreground space-y-2">
          {!hasMatches && <li className="italic">No matching FAQs found.</li>}
          {hasMatches &&
            matches.map((match, index) => (
              <li key={`${event.id}-${index}`} className="space-y-1">
                <p className="leading-snug">{match.text}</p>
                {typeof match.score === 'number' && (
                  <p className="text-muted-foreground/70 text-xs tracking-tight">
                    Relevance: {match.score.toFixed(2)}
                  </p>
                )}
              </li>
            ))}
        </ol>
      </div>
    </details>
  );
}
