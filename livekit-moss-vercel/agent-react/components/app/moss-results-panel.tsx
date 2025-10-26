import * as React from 'react';
import type { MossContextEvent } from '@/hooks/useMossContextEvents';
import { cn } from '@/lib/utils';

interface MossResultsPanelProps extends React.HTMLAttributes<HTMLDivElement> {
  events: MossContextEvent[];
  hidden?: boolean;
}

export function MossResultsPanel({
  events,
  hidden = false,
  className,
  ...props
}: MossResultsPanelProps) {
  if (hidden || events.length === 0) {
    return null;
  }

  return (
    <div className={cn('space-y-3', className)} {...props}>
      <h3 className="text-muted-foreground text-sm font-medium tracking-wide uppercase">
        Knowledge Matches
      </h3>
      <div className="space-y-2">
        {events.map(({ id, query, matches, timeTakenMs }) => (
          <details
            key={id}
            className="border-border bg-card text-card-foreground rounded-lg border p-3 shadow-sm"
            open
          >
            <summary className="cursor-pointer text-sm font-semibold">
              {query}
              {typeof timeTakenMs === 'number' && (
                <span className="text-muted-foreground ml-2 text-xs">
                  {timeTakenMs.toFixed(0)} ms
                </span>
              )}
            </summary>
            <ol className="text-muted-foreground mt-2 space-y-2 text-sm">
              {matches.length === 0 ? (
                <li className="italic">No matching FAQs found.</li>
              ) : (
                matches.map((match, index) => (
                  <li key={`${id}-${index}`} className="space-y-1">
                    <p className="leading-snug">{match.text}</p>
                    {typeof match.score === 'number' && (
                      <p className="text-muted-foreground text-xs">
                        Relevance: {match.score.toFixed(2)}
                      </p>
                    )}
                  </li>
                ))
              )}
            </ol>
          </details>
        ))}
      </div>
    </div>
  );
}
