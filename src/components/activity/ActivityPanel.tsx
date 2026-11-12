import { RefreshCw, X } from 'lucide-react';
import { cn, formatRelativeTime } from '@/lib/utils';
import type { ActivityEvent, ActivityLevel, ActivityStatus, ActivityTab } from '@/types';

const statusClasses: Record<ActivityStatus, string> = {
  pending: 'opacity-50',
  running: 'opacity-100',
  success: 'text-emerald-300',
  failed: 'text-red-300',
  cancelled: 'text-yellow-300',
};

const statusDotClasses: Record<ActivityStatus, string> = {
  pending: 'bg-graphite-500',
  running: 'bg-accent-blue',
  success: 'bg-emerald-400',
  failed: 'bg-red-400',
  cancelled: 'bg-yellow-400',
};

const levelClasses: Record<ActivityLevel, string> = {
  debug: 'text-graphite-500',
  info: 'text-graphite-300',
  warning: 'text-yellow-300',
  error: 'text-red-300',
  critical: 'text-red-200',
};

export interface ActivityEventCardProps {
  event: ActivityEvent;
  onSelect?: () => void;
}

export const ActivityEventCard = ({ event, onSelect }: ActivityEventCardProps) => {
  const duration = event.durationMs != null ? `${event.durationMs}ms` : '-';

  return (
    <button
      type="button"
      className={cn(
        'flex w-full items-start gap-3 rounded px-3 py-2 text-left transition-colors duration-fast hover:bg-graphite-800',
        statusClasses[event.status]
      )}
      onClick={onSelect}
    >
      <span className={cn('mt-1.5 h-1.5 w-1.5 flex-shrink-0 rounded-full', statusDotClasses[event.status])} />
      <span className="min-w-0 flex-1">
        <span className={cn('block text-xs font-medium', levelClasses[event.level])}>{event.title}</span>
        {event.description && (
          <span className="mt-0.5 block truncate text-[0.75em] text-graphite-500">{event.description}</span>
        )}
        {duration !== '-' && <span className="mt-0.5 block text-[0.65em] text-graphite-600">{duration}</span>}
      </span>
      <span className="ml-2 text-[0.65em] font-medium text-graphite-400">{event.status}</span>
      <span className="ml-3 text-[0.65em] text-graphite-500">{formatRelativeTime(event.timestamp)}</span>
    </button>
  );
};

ActivityEventCard.displayName = 'ActivityEventCard';

export interface ActivityPanelProps {
  isOpen: boolean;
  activeTab: ActivityTab;
  onTabChange: (tab: ActivityTab) => void;
  onClose: () => void;
  events?: ActivityEvent[];
  onEventSelect?: (event: ActivityEvent) => void;
}

const tabs: Array<{ id: ActivityTab; label: string }> = [
  { id: 'agents', label: 'Agents' },
  { id: 'tasks', label: 'Tasks' },
  { id: 'tools', label: 'Tools' },
];

export const ActivityPanel = ({
  isOpen,
  activeTab,
  onTabChange,
  onClose,
  events = [],
  onEventSelect,
}: ActivityPanelProps) => {
  return (
    <aside
      className={cn(
        'h-full w-80 max-w-full flex-shrink-0 flex-col border-l border-border-subtle bg-graphite-950 shadow-elevation',
        isOpen ? 'flex' : 'hidden'
      )}
      aria-hidden={!isOpen}
    >
      <div className="flex items-center justify-between border-b border-border-subtle px-4 py-3">
        <h2 className="text-lg font-semibold text-graphite-100">Activity Panel</h2>
        <button
          type="button"
          className="rounded-md p-1 text-graphite-400 hover:bg-graphite-800 hover:text-graphite-100"
          onClick={onClose}
          aria-label="Close panel"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      <div className="flex border-b border-border-subtle">
        {tabs.map((tab) => (
          <button
            type="button"
            key={tab.id}
            className={cn(
              'flex-1 border-b-2 px-3 py-2 text-xs font-medium transition-colors',
              activeTab === tab.id
                ? 'border-accent-blue text-accent-blue'
                : 'border-transparent text-graphite-400 hover:text-graphite-100'
            )}
            onClick={() => onTabChange(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {events.length > 0 ? (
        <div className="min-h-0 flex-1 overflow-y-auto p-1">
          {events.map((event) => (
            <ActivityEventCard key={event.id} event={event} onSelect={() => onEventSelect?.(event)} />
          ))}
        </div>
      ) : (
        <div className="flex flex-1 flex-col items-center justify-center p-6 text-center text-graphite-500">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1">
            <circle cx="12" cy="12" r="10" />
            <line x1="8" y1="12" x2="16" y2="12" />
          </svg>
          <p className="mt-2">No activity events yet</p>
        </div>
      )}

      <div className="flex items-center justify-between border-t border-border-subtle p-4">
        <p className="text-xs text-graphite-400">Last updated just now</p>
        <button
          type="button"
          onClick={() => window.location.reload()}
          className="flex items-center gap-1 text-xs text-accent-blue hover:underline"
        >
          <RefreshCw className="h-3 w-3" />
          Refresh
        </button>
      </div>
    </aside>
  );
};

ActivityPanel.displayName = 'ActivityPanel';

export default ActivityPanel;
