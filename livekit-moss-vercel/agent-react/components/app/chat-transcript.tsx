'use client';

import { useMemo } from 'react';
import { AnimatePresence, type HTMLMotionProps, motion } from 'motion/react';
import { type ReceivedChatMessage } from '@livekit/components-react';
import { MossMatchCard } from '@/components/app/moss-match-card';
import { ChatEntry } from '@/components/livekit/chat-entry';
import type { MossContextEvent } from '@/hooks/useMossContextEvents';

const MotionContainer = motion.create('div');
const MotionChatEntry = motion.create(ChatEntry);
const MotionMossMatchCard = motion.create(MossMatchCard);

const CONTAINER_MOTION_PROPS = {
  variants: {
    hidden: {
      opacity: 0,
      transition: {
        ease: 'easeOut',
        duration: 0.3,
        staggerChildren: 0.1,
        staggerDirection: -1,
      },
    },
    visible: {
      opacity: 1,
      transition: {
        delay: 0.2,
        ease: 'easeOut',
        duration: 0.3,
        stagerDelay: 0.2,
        staggerChildren: 0.1,
        staggerDirection: 1,
      },
    },
  },
  initial: 'hidden',
  animate: 'visible',
  exit: 'hidden',
};

const MESSAGE_MOTION_PROPS = {
  variants: {
    hidden: {
      opacity: 0,
      translateY: 10,
    },
    visible: {
      opacity: 1,
      translateY: 0,
    },
  },
};

interface ChatTranscriptProps {
  hidden?: boolean;
  messages?: ReceivedChatMessage[];
  mossEvents?: MossContextEvent[];
}

type TimelineItem =
  | {
      kind: 'message';
      key: string;
      timestamp: number;
      payload: ReceivedChatMessage;
      order: number;
    }
  | {
      kind: 'moss';
      key: string;
      timestamp: number;
      payload: MossContextEvent;
      order: number;
    };

export function ChatTranscript({
  hidden = false,
  messages = [],
  mossEvents = [],
  ...props
}: ChatTranscriptProps & Omit<HTMLMotionProps<'div'>, 'ref'>) {
  const timeline = useMemo<TimelineItem[]>(() => {
    const messageItems = messages.map((message) => ({
      kind: 'message' as const,
      key: `message-${message.id}`,
      timestamp: message.timestamp ?? 0,
      payload: message,
      order: 0,
    }));

    const eventItems = mossEvents.map((event, index) => ({
      kind: 'moss' as const,
      key: `moss-${event.id ?? index}`,
      timestamp: event.timestamp ?? 0,
      payload: event,
      order: index,
    }));

    const priority: Record<TimelineItem['kind'], number> = {
      message: 0,
      moss: 1,
    };

    return [...messageItems, ...eventItems].sort((a, b) => {
      if (a.timestamp === b.timestamp) {
        if (a.kind === b.kind) {
          if (a.kind !== 'message') {
            return (a.order ?? 0) - (b.order ?? 0);
          }
          return 0;
        }
        return priority[a.kind] - priority[b.kind];
      }
      return a.timestamp - b.timestamp;
    });
  }, [messages, mossEvents]);

  return (
    <AnimatePresence>
      {!hidden && (
        <MotionContainer {...CONTAINER_MOTION_PROPS} {...props}>
          {timeline.map((item) => {
            if (item.kind === 'message') {
              const { payload: chatMessage } = item;
              const { timestamp, from, message, editTimestamp } = chatMessage;
              const locale = navigator?.language ?? 'en-US';
              const messageOrigin = from?.isLocal ? 'local' : 'remote';
              const hasBeenEdited = !!editTimestamp;

              return (
                <MotionChatEntry
                  key={item.key}
                  locale={locale}
                  timestamp={timestamp}
                  message={message}
                  messageOrigin={messageOrigin}
                  hasBeenEdited={hasBeenEdited}
                  {...MESSAGE_MOTION_PROPS}
                />
              );
            }

            return (
              <MotionMossMatchCard key={item.key} event={item.payload} {...MESSAGE_MOTION_PROPS} />
            );
          })}
        </MotionContainer>
      )}
    </AnimatePresence>
  );
}
