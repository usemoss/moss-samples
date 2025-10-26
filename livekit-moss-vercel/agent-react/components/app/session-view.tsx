'use client';

import React, { useMemo, useState } from 'react';
import { motion } from 'motion/react';
import type { AppConfig } from '@/app-config';
import { ChatTranscript } from '@/components/app/chat-transcript';
import { PreConnectMessage } from '@/components/app/preconnect-message';
import { TileLayout } from '@/components/app/tile-layout';
import {
  AgentControlBar,
  type ControlBarControls,
} from '@/components/livekit/agent-control-bar/agent-control-bar';
import { useChatMessages } from '@/hooks/useChatMessages';
import { useConnectionTimeout } from '@/hooks/useConnectionTimout';
import { useDebugMode } from '@/hooks/useDebug';
import { useLlmUsageEvents } from '@/hooks/useLlmUsageEvents';
import { useMossContextEvents } from '@/hooks/useMossContextEvents';
import { cn } from '@/lib/utils';
import { ScrollArea } from '../livekit/scroll-area/scroll-area';

const MotionBottom = motion.create('div');

const IN_DEVELOPMENT = process.env.NODE_ENV !== 'production';
const BOTTOM_VIEW_MOTION_PROPS = {
  variants: {
    visible: {
      opacity: 1,
      translateY: '0%',
    },
    hidden: {
      opacity: 0,
      translateY: '100%',
    },
  },
  initial: 'hidden',
  animate: 'visible',
  exit: 'hidden',
  transition: {
    duration: 0.3,
    delay: 0.5,
    ease: 'easeOut',
  },
};

interface FadeProps {
  top?: boolean;
  bottom?: boolean;
  className?: string;
}

export function Fade({ top = false, bottom = false, className }: FadeProps) {
  return (
    <div
      className={cn(
        'from-background pointer-events-none h-4 bg-linear-to-b to-transparent',
        top && 'bg-linear-to-b',
        bottom && 'bg-linear-to-t',
        className
      )}
    />
  );
}
interface SessionViewProps {
  appConfig: AppConfig;
}

export const SessionView = ({
  appConfig,
  ...props
}: React.ComponentProps<'section'> & SessionViewProps) => {
  useConnectionTimeout(200_000);
  useDebugMode({ enabled: IN_DEVELOPMENT });

  const messages = useChatMessages();
  const mossEvents = useMossContextEvents();
  const llmUsageEvents = useLlmUsageEvents();
  const [chatOpen, setChatOpen] = useState(false);

  const tokenTotals = useMemo(() => {
    let prompt = 0;
    let completion = 0;
    let total = 0;

    for (const event of llmUsageEvents) {
      if (typeof event.promptTokens === 'number' && Number.isFinite(event.promptTokens)) {
        prompt += event.promptTokens;
      }
      if (typeof event.completionTokens === 'number' && Number.isFinite(event.completionTokens)) {
        completion += event.completionTokens;
      }
      if (typeof event.totalTokens === 'number' && Number.isFinite(event.totalTokens)) {
        total += event.totalTokens;
      }
    }

    if (total === 0) {
      total = prompt + completion;
    }

    return {
      prompt,
      completion,
      total,
    };
  }, [llmUsageEvents]);

  const formatTokens = (value: number) =>
    Number.isFinite(value) && value > 0 ? value.toLocaleString() : '0';

  const controls: ControlBarControls = {
    leave: true,
    microphone: true,
    chat: appConfig.supportsChatInput,
    camera: appConfig.supportsVideoInput,
    screenShare: appConfig.supportsVideoInput,
  };

  return (
    <section className="bg-background relative z-10 h-full w-full overflow-hidden" {...props}>
      {/* Chat Transcript */}
      <div
        className={cn(
          'fixed inset-0 grid grid-cols-1 grid-rows-1',
          !chatOpen && 'pointer-events-none'
        )}
      >
        <Fade top className="absolute inset-x-4 top-0 h-40" />
        <ScrollArea className="px-4 pt-40 pb-[150px] md:px-6 md:pb-[180px]">
          <div className="mx-auto max-w-2xl space-y-4 transition-opacity duration-300 ease-out">
            <ChatTranscript
              hidden={!chatOpen}
              messages={messages}
              mossEvents={mossEvents}
              className="space-y-3"
            />
          </div>
        </ScrollArea>
      </div>

      {/* Tile Layout */}
      <TileLayout chatOpen={chatOpen} />

      {/* Bottom */}
      <MotionBottom
        {...BOTTOM_VIEW_MOTION_PROPS}
        className="fixed inset-x-3 bottom-0 z-50 md:inset-x-12"
      >
        {appConfig.isPreConnectBufferEnabled && (
          <PreConnectMessage messages={messages} className="pb-4" />
        )}
        <div className="bg-background relative mx-auto max-w-2xl pb-3 md:pb-12">
          <Fade bottom className="absolute inset-x-0 top-0 h-4 -translate-y-full" />
          <div className="border-border/60 bg-muted/40 text-muted-foreground mb-3 flex flex-wrap items-center gap-3 rounded-lg border px-3 py-2 text-xs">
            <span className="text-muted-foreground/80 text-[11px] font-semibold tracking-wide uppercase">
              Session tokens
            </span>
            <span className="text-foreground text-sm font-semibold">
              Input: {formatTokens(tokenTotals.prompt)}
            </span>
            <span className="text-foreground text-sm font-semibold">
              Output: {formatTokens(tokenTotals.completion)}
            </span>
            <span className="bg-primary/10 text-primary ml-auto rounded-full px-2 py-0.5 text-[11px] font-semibold tracking-wide uppercase">
              Total {formatTokens(tokenTotals.total)}
            </span>
          </div>
          <AgentControlBar controls={controls} onChatOpenChange={setChatOpen} />
        </div>
      </MotionBottom>
    </section>
  );
};
