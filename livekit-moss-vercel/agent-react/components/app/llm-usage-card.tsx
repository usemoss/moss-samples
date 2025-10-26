import * as React from 'react';
import type { LlmUsageEvent } from '@/hooks/useLlmUsageEvents';
import { cn } from '@/lib/utils';

function formatTokens(value?: number | null) {
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    return '—';
  }
  return value.toLocaleString();
}

interface LlmUsageCardProps extends React.HTMLAttributes<HTMLDivElement> {
  event: LlmUsageEvent;
}

export function LlmUsageCard({ event, className, ...props }: LlmUsageCardProps) {
  const { model, completionTokens, totalTokens } = event;
  const responseTokens = completionTokens ?? totalTokens ?? null;

  return (
    <div
      className={cn(
        'supports-[backdrop-filter]:bg-card/60 bg-secondary/40 text-secondary-foreground border-secondary/50 border-l-primary/60 shadow-primary/10 rounded-lg border border-l-4 p-3 shadow-sm backdrop-blur',
        className
      )}
      {...props}
    >
      <header className="flex flex-wrap items-center gap-3 text-sm">
        <span className="text-muted-foreground/80 text-[11px] font-semibold tracking-wide uppercase">
          Agent response tokens
        </span>
        {model && (
          <span className="text-muted-foreground/70 truncate text-xs font-medium">{model}</span>
        )}
        <span className="bg-primary/10 text-primary ml-auto rounded-full px-2 py-0.5 text-[11px] font-semibold tracking-wide uppercase">
          {formatTokens(responseTokens)} tokens
        </span>
      </header>
      <div className="text-muted-foreground/80 mt-3 text-xs">
        <p className="text-foreground text-sm font-semibold">
          {formatTokens(responseTokens)} tokens generated for this answer
        </p>
      </div>
    </div>
  );
}
