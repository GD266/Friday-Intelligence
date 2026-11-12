import { type ReactNode } from 'react';
import { cn } from '../../lib/utils';

export interface ActivityEventCardProps {
  event: any;
  onSelect?: () => void;
}

export const ActivityEventCard = ({ event, onSelect }: ActivityEventCardProps) => {
  const statusClasses = {
    pending: 'opacity-50',
    running: 'opacity-100',
    success: 'text-emerald-300',
    failed: 'text-red-300',
    cancelled: 'text-yellow-300',
  };

  const duration = event.durationMs != null ? `${event.durationMs}ms` : '-';

  return (
    <div
      className={cn(
        'flex items-start gap-3 px-3 py-2 rounded transition-colors duration-fast hover:bg-graphite-800',
        statusClasses[event.status] ?? ''
      )}
    >
      <div className={cn('w-1.5 h-1.5 rounded-full', statusClasses[event.status] ?? 'bg-graphite-600')} />
      <div className="flex-1 min-w-0">
        <p className={cn('text-xs font-medium', event.level && `text-graphite-${event.level === 'error' ? '400' : event.level === 'warning' ? '500' : '300'}`)}>
          {event.title}
        </p>
        {event.description != null && <p className="mt-0.5 text-[0.75em] text-graphite-500 truncate-multiline">{event.description}</p>}
      </div>
      <span className={cn('ml-2 text-[0.65em] font-medium rounded', statusClasses[event.status] ?? 'bg-graphite-500/20 text-graphite-400')}>
        {event.status ?? 'pending'}
      </span>
      <span className="ml-3 text-[0.65em] opacity-60">
        {event.timestamp != null ? `${Math.floor((new Date().getTime() - event.timestamp.getTime()) / 60000)}m ago` : ''}
      </span>
    </div>
  );
};

ActivityEventCard.displayName = 'ActivityEventCard';

export interface ActivityPanelProps {
  isOpen?: boolean;
  onToggle?: () => void;
  events?: any[];
  onEventSelect?: (event: any) => void;
}

export const ActivityPanel = ({
  isOpen,
  onToggle,
  events,
  onEventSelect,
}: ActivityPanelProps) => {
  const recentEvents = events != null && events.length > 0 ? events : [];

  return (
    <aside
      className={cn(
        'w-80 max-w-full bg-graphite-950 border-l-4 border-border-subtle shadow-elevation flex-shrink-0 right-0 top-20 transform transition-transform duration-300 ease-out',
        isOpen ? 'translateX(0)' : 'translateX(-280px)'
      )}
      style={{ right: isOpen ? 0 : -280 }}
    >
      <div className="flex items-center justify-between px-4 py-3 border-b border-border-subtle">
        <h2 className="text-lg font-semibold text-graphite-100">Activity Panel</h2>
        <button onClick={onToggle} aria-label="Close panel">
          ✕
        </button>
      </div>
      <div className="border-b border-border-subtle flex">
        <button onClick={() => onToggle?.('agents')}>Agents</button>
        <button onClick={() => onToggle?.('tasks')}>Tasks</button>
        <button onClick={() => onToggle?.('tools')}>Tools</button>
      </div>
      {recentEvents.length > 0 ? (
        <div className="flex-1 h-64 overflow-y-auto pr-1">
          {recentEvents.map((event, index) => (
            <ActivityEventCard key={index} event={event} onSelect={() => onEventSelect?.(event)} />
          ))}
        </div>
      ) : (
        <div className="p-6 text-center text-graphite-500">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1">
            <circle cx="12" cy="12" r="10" />
            <line x1="8" y1="12" x2="16" y2="12" />
          </svg>
          <p>No activity events yet</p>
        </div>
      )}
      <div className="p-4 border-t border-border-subtle flex items-center justify-between">
        <p className="text-xs text-graphite-400">Last updated just now</p>
        <button onClick={() => window.location.reload()} className="text-xs text-blue-500 hover:underline">Refresh</button>
      </div>
    </aside>
  );
};

ActivityPanel.displayName = 'ActivityPanel';

export default ActivityPanel;