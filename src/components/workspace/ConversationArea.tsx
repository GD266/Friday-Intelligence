import { useState, type FormEvent } from 'react';
import { Paperclip } from 'lucide-react';
import { cn, formatRelativeTime } from '@/lib/utils';
import type { Message as ConversationMessage } from '@/types';
import { Button } from '../ui/Button';

export interface MessageProps {
  role: 'user' | 'assistant' | 'system' | 'tool';
  content: string;
  metadata?: {
    model?: string;
    timestamp?: Date;
    isStreaming?: boolean;
    isFromCurrentUser?: boolean;
  };
}

export const Message = ({ role, content, metadata }: MessageProps) => {
  const roleClasses = {
    user: 'flex items-end',
    assistant: 'flex items-start',
    system: 'flex items-center text-graphite-500 text-sm italic',
    tool: 'flex items-start text-indigo-300',
  };

  const bubbleClasses = {
    user: 'bg-accent-blue text-white rounded-xl px-4 py-3 max-w-[80%] self-end',
    assistant: 'bg-surface-elevated rounded-xl px-4 py-3 max-w-[80%] self-start border border-border-subtle',
    system: 'bg-graphite-800 rounded text-graphite-500 text-sm px-4 py-3 max-w-[80%] self-center',
    tool: 'bg-indigo-500/20 rounded-xl px-4 py-3 max-w-[80%] self-start text-indigo-300',
  };

  const avatarClasses = {
    user: 'w-6 h-6 rounded-full bg-white flex-shrink-0 self-end',
    assistant: 'w-6 h-6 rounded-full bg-indigo-600 flex-shrink-0 self-start',
    system: 'w-6 h-6 rounded-full bg-graphite-700 flex-shrink-0 self-center',
    tool: 'w-6 h-6 rounded-full bg-indigo-500 flex-shrink-0 self-start',
  };

  const timestamp = metadata?.timestamp ? formatRelativeTime(metadata.timestamp) : '';

  return (
    <div className={cn('w-full mb-3', roleClasses[role])}>
      <div className={cn('flex items-start gap-3', roleClasses[role])}>
        <div className={cn('w-6 h-6 rounded-full flex-shrink-0', avatarClasses[role])} />
        <div className={cn('flex-1', bubbleClasses[role])}>
          <p className="text-graphite-100 break-words whitespace-pre-wrap">{content}</p>
          {timestamp && <p className="mt-1 text-[0.65em] opacity-60">{timestamp}</p>}
        </div>
      </div>
    </div>
  );
};

Message.displayName = 'Message';

export interface MessageInputProps {
  placeholder?: string;
  onSend?: (content: string) => void;
  onAttachment?: () => void;
  isDisabled?: boolean;
  showModelSelector?: boolean;
  currentModel?: string;
}

export const MessageInput = ({
  placeholder = 'Type a message…',
  onSend,
  onAttachment,
  isDisabled = false,
  showModelSelector = true,
  currentModel = 'No model configured',
}: MessageInputProps) => {
  const [inputValue, setInputValue] = useState('');

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const content = inputValue.trim();
    if (!onSend || !content || isDisabled) return;
    onSend(content);
    setInputValue('');
  };

  return (
    <form
      className="flex items-end gap-3 p-4 border-t border-border-subtle bg-graphite-950"
      onSubmit={handleSubmit}
    >
      <button
        type="button"
        className="p-1.5 rounded-md hover:bg-graphite-800 transition-colors flex-shrink-0"
        onClick={onAttachment}
        aria-label="Attach file"
        disabled={isDisabled}
      >
        <Paperclip className="h-4 w-4" />
      </button>

      {showModelSelector && (
        <span className="hidden sm:inline-flex px-2 py-1 rounded bg-surface-elevated border border-border-primary text-xs text-graphite-400">
          {currentModel}
        </span>
      )}

      <div className="flex-1 flex gap-2">
        <input
          placeholder={placeholder}
          value={inputValue}
          onChange={(event) => setInputValue(event.target.value)}
          disabled={isDisabled}
          className="w-full px-3 py-2 bg-surface-elevated border text-graphite-100 placeholder-graphite-500 rounded transition-all duration-fast focus:outline-none focus:border-accent-blue focus:ring-1 focus:ring-accent-blue disabled:opacity-40 disabled:cursor-not-allowed"
        />

        <Button
          type="submit"
          variant="primary"
          size="sm"
          disabled={!inputValue.trim() || isDisabled}
        >
          Send
        </Button>
      </div>
    </form>
  );
};

MessageInput.displayName = 'MessageInput';

export interface ConversationAreaProps {
  messages: ConversationMessage[];
  onMessageAdded?: (content: string) => void;
  showModelSelector?: boolean;
}

export const ConversationArea = ({
  messages,
  onMessageAdded,
  showModelSelector = true,
}: ConversationAreaProps) => {
  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex-1 overflow-y-auto pr-4">
        {messages.map((message) => (
          <Message
            key={message.id}
            role={message.role}
            content={message.content.text ?? ''}
            metadata={{
              model: message.metadata.modelId,
              timestamp: message.createdAt,
              isStreaming: message.metadata.isStreaming,
            }}
          />
        ))}

        {messages.length === 0 && (
          <div className="flex h-full min-h-64 flex-col items-center justify-center p-8 text-center text-graphite-500">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1">
              <circle cx="12" cy="12" r="10" />
              <line x1="8" y1="12" x2="16" y2="12" />
            </svg>
            <p className="mt-2">Start a conversation by sending a message</p>
          </div>
        )}
      </div>

      {onMessageAdded && <MessageInput onSend={onMessageAdded} showModelSelector={showModelSelector} />}
    </div>
  );
};

ConversationArea.displayName = 'ConversationArea';
