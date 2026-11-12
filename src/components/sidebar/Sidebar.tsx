import { type ReactNode } from 'react';
import {
  Bot,
  Brain,
  FolderKanban,
  MessageSquare,
  PanelLeftClose,
  PanelLeftOpen,
  Settings,
  Workflow,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import type { SidebarSection as SidebarSectionId } from '@/types';

export interface SidebarItemProps {
  icon: ReactNode;
  label: string;
  onClick?: () => void;
  isActive?: boolean;
  isCollapsed?: boolean;
  isDanger?: boolean;
  disabled?: boolean;
}

export const SidebarItem = ({
  icon,
  label,
  onClick,
  isActive = false,
  isCollapsed = false,
  isDanger = false,
  disabled = false,
}: SidebarItemProps) => {
  return (
    <button
      type="button"
      className={cn(
        'flex w-full items-center gap-3 rounded px-3 py-2 text-sm font-medium transition-all duration-fast',
        'text-graphite-400 hover:bg-graphite-800 hover:text-graphite-100',
        isActive && 'bg-accent-blue/10 text-accent-blue border-l-2 border-accent-blue',
        isDanger && 'text-red-400 hover:bg-red-600/10 hover:text-red-300',
        disabled && 'cursor-not-allowed opacity-40',
        isCollapsed && 'justify-center px-2'
      )}
      onClick={onClick}
      disabled={disabled}
      aria-current={isActive ? 'page' : undefined}
      title={isCollapsed ? label : undefined}
    >
      {icon}
      {!isCollapsed && <span>{label}</span>}
    </button>
  );
};

SidebarItem.displayName = 'SidebarItem';

export interface SidebarSectionProps {
  title: string;
  description?: string;
  icon?: ReactNode;
}

export const SidebarSection = ({ title, description, icon }: SidebarSectionProps) => (
  <div className="mb-2 flex items-center gap-2 p-2 text-xs font-medium uppercase tracking-wider text-graphite-500">
    {icon}
    <span>{title}</span>
    {description && (
      <span className="ml-1 rounded bg-graphite-900/50 px-1 text-[0.65em] opacity-50">{description}</span>
    )}
  </div>
);

SidebarSection.displayName = 'SidebarSection';

export interface SidebarProps {
  activeSection: SidebarSectionId;
  onSectionChange: (section: SidebarSectionId) => void;
  isCollapsed?: boolean;
  onToggleCollapse?: () => void;
}

export const Sidebar = ({
  activeSection,
  onSectionChange,
  isCollapsed = false,
  onToggleCollapse,
}: SidebarProps) => {
  const navItems: Array<{ id: SidebarSectionId; label: string; icon: ReactNode }> = [
    { id: 'conversations', label: 'Conversations', icon: <MessageSquare className="h-4 w-4 flex-shrink-0" /> },
    { id: 'projects', label: 'Projects', icon: <FolderKanban className="h-4 w-4 flex-shrink-0" /> },
    { id: 'agents', label: 'Agents', icon: <Bot className="h-4 w-4 flex-shrink-0" /> },
    { id: 'memory', label: 'Memory', icon: <Brain className="h-4 w-4 flex-shrink-0" /> },
    { id: 'automation', label: 'Automation', icon: <Workflow className="h-4 w-4 flex-shrink-0" /> },
    { id: 'settings', label: 'Settings', icon: <Settings className="h-4 w-4 flex-shrink-0" /> },
  ];

  const collapsedWidth = 80;
  const expandedWidth = 280;

  return (
    <aside
      className="h-full flex-shrink-0 border-r border-border-subtle bg-graphite-950 transition-[width] duration-200"
      style={{ width: isCollapsed ? collapsedWidth : expandedWidth }}
    >
      <div className="flex h-full flex-col">
        <header className={cn('flex h-20 items-center justify-between pt-3', isCollapsed ? 'px-2' : 'px-4')}>
          <div className="flex items-center gap-3">
            <div className="flex h-8 w-8 items-center justify-center rounded-md bg-accent-blue text-white">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                <rect x="3" y="11" width="18" height="11" rx="2" />
                <path d="M7 11V7a5 5 0 0 1 10 0v4" />
              </svg>
            </div>
            {!isCollapsed && <span className="text-lg font-semibold">FRIDAY Intelligence</span>}
          </div>
          <button
            type="button"
            className="rounded-md p-1.5 text-graphite-400 hover:bg-graphite-800 hover:text-graphite-100"
            onClick={onToggleCollapse}
            aria-label={isCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          >
            {isCollapsed ? <PanelLeftOpen className="h-4 w-4" /> : <PanelLeftClose className="h-4 w-4" />}
          </button>
        </header>

        <nav className="flex-1 overflow-y-auto px-2 py-2">
          {!isCollapsed && <SidebarSection title="Navigate" />}
          <div className="space-y-1">
            {navItems.map((item) => (
              <SidebarItem
                key={item.id}
                icon={item.icon}
                label={item.label}
                isActive={activeSection === item.id}
                isCollapsed={isCollapsed}
                onClick={() => onSectionChange(item.id)}
              />
            ))}
          </div>
        </nav>

        <footer className={cn('border-t border-border-subtle p-4', isCollapsed && 'text-center')}>
          <div className="text-xs text-graphite-500">v0.1.0</div>
        </footer>
      </div>
    </aside>
  );
};

Sidebar.displayName = 'Sidebar';

export default Sidebar;
