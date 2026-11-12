import { type ReactNode } from 'react';
import { cn } from '../../lib/utils';

export interface TopBarProps {
  title?: string;
  subtitle?: string;
  actions?: ReactNode;
  onNewConversation?: () => void;
  onToggleSidebar?: () => void;
  onToggleActivity?: () => void;
  isConnected?: boolean;
  currentModel?: string;
  currentProvider?: string;
  showActivityPanel?: boolean;
}

export const TopBar = ({
  title = 'FRIDAY Intelligence',
  subtitle = 'Premium AI Desktop Workspace',
  actions,
  onNewConversation,
  onToggleSidebar,
  onToggleActivity,
  isConnected = false,
  currentModel = 'Llama 3.1 8B',
  currentProvider = 'Ollama',
  showActivityPanel = false,
}: TopBarProps) => {
  const connectedClass = 'bg-green-600/20 text-green-400';
  const disconnectedClass = 'bg-red-600/20 text-red-400';

  return (
    <header
      className={cn(
        'flex items-center justify-between h-14 border-b border-border-subtle bg-graphite-950 px-4 shadow-subtle'
      )}
    >
      <div className="flex items-center gap-3">
        <h1 className="text-lg font-semibold text-graphite-100 tracking-tight">{title}</h1>
        <p className="text-sm text-graphite-400 truncate-multiline max-w-xs">{subtitle}</p>
      </div>

      <div className="flex items-center gap-3">
        <div className={cn('flex items-center gap-2', isConnected ? connectedClass : disconnectedClass)}>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor">
            <circle cx="12" cy="12" r="5" />
            <path d="M12 1v4m0 12v4M4.93 4.93l2.83 2.83m8.95 8.95l2.83 2.83M2 12h8M12 20h.01M4.93 19.07l2.83-2.83m8.95-8.95l2.83-2.83" />
          </svg>
          <span className="text-xs font-medium text-graphite-300">{isConnected ? 'Connected' : 'Disconnected'}</span>
        </div>

        <div className="flex items-center gap-1.5 px-2.5 py-1.5 rounded bg-surface-elevated border border-border-primary text-xs text-graphite-300">
          {currentProvider}
        </div>

        <button
          className="relative hidden sm:flex items-center gap-1.5 px-2.5 py-1.5 rounded border border-border-primary text-xs text-graphite-300 hover:bg-graphite-800"
          aria-label="Switch model"
        >
          ▼
          <span>{currentModel}</span>
        </button>

        <button
          className="relative p-1.5 rounded-md hover:bg-graphite-800"
          onClick={onToggleActivity}
          aria-label="Toggle activity panel"
        >
          Activity
        </button>

        <button
          className="btn btn-primary"
          onClick={onNewConversation}
          aria-label="New conversation"
        >
          New
        </button>

        <button
          className="relative p-1.5 rounded-md hover:bg-graphite-800"
          aria-label="Settings"
        >
          ⚙️
        </button>
      </div>
    </header>
  );
};

TopBar.displayName = 'TopBar';

export default TopBar;