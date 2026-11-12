import { useEffect, useRef } from 'react';
import { CornerDownRight, MessageSquarePlus, Plus, ScrollText, Sparkles } from 'lucide-react';
import { cn, formatRelativeTime } from '@/lib/utils';
import { useAssistantStore, useConversationsStore } from '@/stores';
import { Overlay } from './Overlay';

export interface TransmissionLogProps {
  onClose: () => void;
}

const roleLabel: Record<string, string> = {
  assistant: 'FRIDAY',
  user: 'DIRECTIVE',
  system: 'SYSTEM',
  tool: 'TOOL',
};

const clock = (date: Date) =>
  new Intl.DateTimeFormat('en-GB', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  }).format(date);

export const TransmissionLog = ({ onClose }: TransmissionLogProps) => {
  const conversations = useConversationsStore((state) => state.conversations);
  const activeConversationId = useConversationsStore((state) => state.activeConversationId);
  const setActiveConversation = useConversationsStore((state) => state.setActiveConversation);
  const createConversation = useConversationsStore((state) => state.createConversation);
  const mood = useAssistantStore((state) => state.mood);
  const scrollRef = useRef<HTMLDivElement>(null);

  const activeConversation =
    conversations.find((conversation) => conversation.id === activeConversationId) ?? null;
  const messages = activeConversation?.messages ?? [];
  const isThinking = mood === 'thinking';

  useEffect(() => {
    const node = scrollRef.current;
    if (node) node.scrollTop = node.scrollHeight;
  }, [messages.length, isThinking, activeConversationId]);

  const handleNewSession = () => {
    createConversation();
    onClose();
  };

  return (
    <Overlay
      eyebrow="Core memory / archived exchanges"
      title="Transmission log"
      description="Every local directive and response, preserved in your workspace."
      onClose={onClose}
      width="wide"
      height="tall"
      accessory={
        <button
          type="button"
          onClick={handleNewSession}
          className="hidden items-center gap-2 rounded border border-cyan-300/20 bg-cyan-300/[0.06] px-3 py-1.5 font-mono text-[0.6rem] uppercase tracking-[0.14em] text-cyan-200 transition-colors hover:bg-cyan-300/10 sm:flex"
        >
          <Plus className="h-3 w-3" />
          new session
        </button>
      }
    >
      <div className="flex h-full min-h-0">
        <aside className="hidden w-56 flex-shrink-0 flex-col border-r border-white/[0.06] md:flex">
          <div className="border-b border-white/[0.05] px-3 py-3">
            <p className="font-mono text-[0.55rem] uppercase tracking-[0.2em] text-graphite-600">
              session archive
            </p>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto scrollbar-thin p-2">
            {conversations.length === 0 ? (
              <p className="px-2 py-4 font-mono text-[0.62rem] leading-relaxed text-graphite-600">
                No sessions recorded yet. Send a directive to start one.
              </p>
            ) : (
              conversations.map((conversation) => {
                const isActive = conversation.id === activeConversationId;
                return (
                  <button
                    key={conversation.id}
                    type="button"
                    onClick={() => setActiveConversation(conversation.id)}
                    className={cn(
                      'mb-1 flex w-full flex-col items-start gap-1 rounded border px-2.5 py-2 text-left transition-colors',
                      isActive
                        ? 'border-cyan-300/20 bg-cyan-300/[0.06]'
                        : 'border-transparent text-graphite-400 hover:border-white/[0.06] hover:bg-white/[0.02]'
                    )}
                  >
                    <span className="flex w-full items-center gap-2">
                      <span
                        className={cn(
                          'h-1 w-1 flex-shrink-0 rounded-full',
                          isActive ? 'bg-cyan-300' : 'bg-graphite-600'
                        )}
                      />
                      <span
                        className={cn(
                          'min-w-0 flex-1 truncate text-xs',
                          isActive ? 'text-graphite-100' : 'text-graphite-400'
                        )}
                      >
                        {conversation.title}
                      </span>
                    </span>
                    <span className="pl-3 font-mono text-[0.52rem] uppercase tracking-wider text-graphite-600">
                      {formatRelativeTime(new Date(conversation.updatedAt))} ·{' '}
                      {conversation.messages.length} msg
                    </span>
                  </button>
                );
              })
            )}
          </div>
          <div className="border-t border-white/[0.05] p-2">
            <button
              type="button"
              onClick={handleNewSession}
              className="flex w-full items-center justify-center gap-2 rounded border border-white/[0.06] px-2 py-2 font-mono text-[0.58rem] uppercase tracking-[0.14em] text-graphite-400 transition-colors hover:border-cyan-300/20 hover:text-cyan-200"
            >
              <MessageSquarePlus className="h-3 w-3" />
              new session
            </button>
          </div>
        </aside>

        <div className="flex min-w-0 flex-1 flex-col">
          <div className="flex flex-shrink-0 items-center justify-between gap-3 border-b border-white/[0.05] px-4 py-3 sm:px-5">
            <div className="flex min-w-0 items-center gap-2.5">
              <ScrollText className="h-3.5 w-3.5 flex-shrink-0 text-cyan-300/70" />
              <p className="truncate font-mono text-[0.65rem] uppercase tracking-[0.14em] text-graphite-300">
                {activeConversation?.title ?? 'unfiled session'}
              </p>
            </div>
            <span className="flex-shrink-0 font-mono text-[0.55rem] uppercase tracking-[0.18em] text-graphite-600">
              {messages.length} transmission{messages.length === 1 ? '' : 's'}
            </span>
          </div>

          <div ref={scrollRef} className="min-h-0 flex-1 overflow-y-auto scrollbar-thin px-4 py-4 sm:px-5">
            {messages.length === 0 && !isThinking ? (
              <div className="flex h-full min-h-[20rem] flex-col items-center justify-center text-center">
                <span className="flex h-14 w-14 items-center justify-center rounded-full border border-cyan-300/15 bg-cyan-300/[0.04]">
                  <Sparkles className="h-5 w-5 text-cyan-300/60" />
                </span>
                <p className="mt-4 font-mono text-[0.62rem] uppercase tracking-[0.22em] text-graphite-500">
                  channel empty
                </p>
                <p className="mt-2 max-w-sm text-sm leading-relaxed text-graphite-500">
                  Return to the core and issue a directive. FRIDAY will keep the exchange here.
                </p>
              </div>
            ) : (
              <div className="space-y-3">
                {messages.map((message) => {
                  const isAssistant = message.role === 'assistant';
                  const isSystem = message.role === 'system' || message.role === 'tool';
                  const createdAt =
                    message.createdAt instanceof Date
                      ? message.createdAt
                      : new Date(message.createdAt);

                  if (isSystem) {
                    return (
                      <div
                        key={message.id}
                        className="flex items-start gap-2 rounded border border-white/[0.05] bg-white/[0.015] px-3 py-2 font-mono text-[0.68rem] text-graphite-500"
                      >
                        <span className="uppercase tracking-wider text-graphite-600">sys</span>
                        <span className="min-w-0 flex-1 break-words text-graphite-400">
                          {message.content.text}
                        </span>
                      </div>
                    );
                  }

                  return (
                    <article
                      key={message.id}
                      className={cn(
                        'transmission-row relative rounded-lg border px-3.5 py-3',
                        isAssistant
                          ? 'border-cyan-300/[0.12] bg-cyan-300/[0.025]'
                          : 'border-white/[0.06] bg-white/[0.02]'
                      )}
                    >
                      <div className="flex items-center gap-2">
                        <span
                          className={cn(
                            'font-mono text-[0.58rem] font-semibold uppercase tracking-[0.2em]',
                            isAssistant ? 'text-cyan-300/80' : 'text-graphite-400'
                          )}
                        >
                          {roleLabel[message.role] ?? message.role}
                        </span>
                        <span className="h-px flex-1 bg-gradient-to-r from-white/[0.06] to-transparent" />
                        <span className="font-mono text-[0.52rem] text-graphite-600">
                          {clock(createdAt)}
                        </span>
                      </div>
                      <p className="mt-2 whitespace-pre-wrap break-words text-sm leading-relaxed text-graphite-200">
                        {message.content.text}
                      </p>
                      {isAssistant && (
                        <CornerDownRight className="absolute -bottom-1 right-3 h-3 w-3 text-cyan-300/20" />
                      )}
                    </article>
                  );
                })}

                {isThinking && (
                  <div className="flex items-center gap-3 rounded border border-cyan-300/[0.12] bg-cyan-300/[0.025] px-3.5 py-3">
                    <span className="flex gap-1">
                      <span className="typing-dot" />
                      <span className="typing-dot" />
                      <span className="typing-dot" />
                    </span>
                    <span className="font-mono text-[0.58rem] uppercase tracking-[0.18em] text-cyan-300/60">
                      core processing
                    </span>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </Overlay>
  );
};

TransmissionLog.displayName = 'TransmissionLog';

export default TransmissionLog;
