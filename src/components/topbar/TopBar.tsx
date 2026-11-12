import { type ReactNode } from 'react';
import { Activity, ChevronDown, PanelLeft, Plus, Settings } from 'lucide-react';
import { cn } from '@/lib/utils';

export interface TopBarProps {
  title?: string;
  subtitle?: string;
  actions?: ReactNode;
  onNewConversation?: () => void;
  onToggleSidebar?: () => void;
  onToggleActivity?: () => void;
  onOpenSettings?: () => void;
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
  onOpenSettings,
  isConnected = false,
  currentModel = 'No model configured',
  currentProvider = 'No provider',
  showActivityPanel = false,
}: TopBarProps) => {
  const connectedClass = 'bg-green-600/20 text-green-400';
  const disconnectedClass = 'bg-red-600/20 text-red-400';

  return (
    <header className="flex h-14 flex-shrink-0 items-center justify-between border-b border-border-subtle bg-graphite-950 px-4 shadow-subtle">
      <div className="flex min-w-0 items-center gap-3">
        <button
          type="button"
          className="rounded-md p-1.5 text-graphite-400 hover:bg-graphite-800 hover:text-graphite-100"
          onClick={onToggleSidebar}
          aria-label="Toggle sidebar"
        >
          <PanelLeft className="h-4 w-4" />
        </button>
        <h1 className="truncate text-lg font-semibold tracking-tight text-graphite-100">{title}</h1>
        <p className="hidden max-w-xs truncate text-sm text-graphite-400 md:block">{subtitle}</p>
      </div>

      <div className="flex items-center gap-2">
        {actions}

        <div className={cn('hidden items-center gap-2 rounded px-2 py-1 lg:flex', isConnected ? connectedClass : disconnectedClass)}>
          <span className={cn('h-1.5 w-1.5 rounded-full', isConnected ? 'bg-green-400' : 'bg-red-400')} />
          <span className="text-xs font-medium text-graphite-300">{isConnected ? 'Connected' : 'Disconnected'}</span>
        </div>

        <div className="hidden items-center gap-1.5 rounded border border-border-primary bg-surface-elevated px-2.5 py-1.5 text-xs text-graphite-300 sm:flex">
          {currentProvider}
        </div>

        <button
          type="button"
          className="relative hidden items-center gap-1.5 rounded border border-border-primary px-2.5 py-1.5 text-xs text-graphite-300 hover:bg-graphite-800 sm:flex"
          aria-label="Switch model"
        >
          <span>{currentModel}</span>
          <ChevronDown className="h-3 w-3" />
        </button>

        <button
          type="button"
          className={cn(
            'relative rounded-md p-1.5 hover:bg-graphite-800',
            showActivityPanel ? 'bg-graphite-800 text-graphite-100' : 'text-graphite-400'
          )}
          onClick={onToggleActivity}
          aria-label="Toggle activity panel"
          aria-pressed={showActivityPanel}
        >
          <Activity className="h-4 w-4" />
        </button>

        <button
          type="button"
          className="btn btn-primary"
          onClick={onNewConversation}
          aria-label="New conversation"
        >
          <Plus className="h-4 w-4" />
          <span className="hidden sm:inline">New</span>
        </button>

        <button
          type="button"
          className="rounded-md p-1.5 text-graphite-400 hover:bg-graphite-800 hover:text-graphite-100"
          onClick={onOpenSettings}
          aria-label="Settings"
        >
          <Settings className="h-4 w-4" />
        </button>
      </div>
    </header>
  );
};

TopBar.displayName = 'TopBar';

export default TopBar;
