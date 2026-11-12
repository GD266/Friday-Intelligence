import { type ReactNode } from 'react';

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

  const timestamp = metadata?.timestamp ? `${Math.floor((new Date().getTime() - metadata.timestamp.getTime()) / 60000)}m ago` : '';

  return (
    <div className={cn('w-full mb-3', roleClasses[role])}>
      <div className={cn('flex items-start gap-3', roleClasses[role])}>
        <div className={cn('w-6 h-6 rounded-full flex-shrink-0', avatarClasses[role])} />
        <div className={cn('flex-1', bubbleClasses[role])}>
          <p className="text-graphite-100 break-words">{content}</p>
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
  currentModel = 'Llama 3.1 8B',
}: MessageInputProps) => {
  const [inputValue, setInputValue] = React.useState('');

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (onSend && inputValue.trim()) {
        onSend(inputValue.trim());
        setInputValue('');
      }
    }
  };

  const handleAttachmentClick = () => {
    onAttachment?.();
  };

  return (
    <div className="flex items-end gap-3 p-4 border-t border-border-subtle bg-graphite-950">
      <button
        className="p-1.5 rounded-md hover:bg-graphite-800 transition-colors flex-shrink-0"
        onClick={handleAttachmentClick}
        aria-label="Attach file"
        disabled={isDisabled}
      >
        ✕
      </button>

      <div className="flex-1 flex gap-2">
        <input
          placeholder={placeholder}
          value={inputValue}
          onValueChange={(e: React.ChangeEvent<HTMLInputElement>) => setInputValue(e.target.value)}
          disabled={isDisabled}
          className="w-full px-3 py-2 bg-surface-elevated border text-graphite-100 placeholder-graphite-500 rounded transition-all duration-fast focus:outline-none focus:border-accent-blue focus:ring-1 focus:ring-accent-blue disabled:opacity-40 disabled:cursor-not-allowed"
        />

        <button
          onClick={() => onSend?.(inputValue.trim())}
          disabled={!inputValue.trim() || isDisabled}
          className="px-3 py-1.5 text-sm font-medium"
        >
          Send
        </button>
      </div>
    </div>
  );
};

MessageInput.displayName = 'MessageInput';

export interface ConversationAreaProps {
  messages: any[];
  onMessageAdded?: (message: any) => void;
  showModelSelector?: boolean;
}

export const ConversationArea = ({
  messages,
  onMessageAdded,
  showModelSelector = true,
}: ConversationAreaProps) => {
  return (
    <div className="flex-1 overflow-y-auto pr-4">
      {messages.map((msg, index) => (
        <Message
          key={msg.id || index}
          role={msg.role}
          content={msg.content.text || msg.content}
          metadata={{
            model: msg.metadata?.modelId,
            timestamp: msg.metadata?.createdAt,
            isStreaming: msg.metadata?.isStreaming,
          }}
        />
      ))}

      {messages.length === 0 && (
        <div className="p-8 text-center text-graphite-500">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1">
            <circle cx="12" cy="12" r="10" />
            <line x1="8" y1="12" x2="16" y2="12" />
          </svg>
          <p>Start a conversation by sending a message</p>
        </div>
      )}
    </div>
  );
};

ConversationArea.displayName = 'ConversationArea';