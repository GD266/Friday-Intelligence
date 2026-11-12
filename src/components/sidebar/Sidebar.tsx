import { type ReactNode } from 'react';
import { cn } from '../../lib/utils';

export interface SidebarItemProps {
  icon: ReactNode;
  label: string;
  onClick?: () => void;
  isActive?: boolean;
  onToggle?: (section: string) => void;
  isDanger?: boolean;
  disabled?: boolean;
}

export const SidebarItem = ({ icon, label, onClick, isActive = false, isDanger = false, disabled = false, onToggle }: SidebarItemProps) => {
  const hoverClasses = 'hover:bg-graphite-800 hover:text-graphite-100';
  const activeClasses = 'bg-accent-blue/10 text-accent-blue border-l-2 border-accent-blue';
  const dangerClasses = 'text-red-400 hover:bg-red-600/10 hover:text-red-300';

  let finalClasses = cn(
    'flex items-center gap-3 w-full px-3 py-2 text-sm font-medium text-graphite-400 rounded transition-all duration-fast',
    isActive ? activeClasses : '',
    disabled && 'cursor-not-allowed opacity-40'
  );

  if (isDanger) {
    finalClasses = cn(finalClasses, dangerClasses);
  } else if (isActive) {
    finalClasses = cn(finalClasses, activeClasses);
  } else {
    finalClasses = cn(finalClasses, hoverClasses);
  }

  return (
    <div className={finalClasses} onClick={onClick} onMouseEnter={() => disabled || onToggle?.(label)}>
      {icon}
      <span>{label}</span>
    </div>
  );
};

SidebarItem.displayName = 'SidebarItem';

export interface SidebarSectionProps {
  title: string;
  description?: string;
  icon?: ReactNode;
}

export const SidebarSection = ({ title, description, icon }: SidebarSectionProps) => (
  <div className="text-xs font-medium text-graphite-500 uppercase tracking-wider mb-2 p-2">
    {title}
    {description && <span className="ml-1 text-[0.65em] opacity-50 bg-graphite-900/50 px-1 rounded">{description}</span>}
  </div>
);

SidebarSection.displayName = 'SidebarSection';

export interface SidebarProps {
  activeSection: string;
  onSectionChange: (section: string) => void;
  isCollapsed?: boolean;
  onToggleCollapse?: () => void;
}

export const Sidebar = ({ activeSection, onSectionChange, isCollapsed = false, onToggleCollapse }: SidebarProps) => {
  const navItems = [
    { id: 'conversations', label: 'Conversations' },
    { id: 'projects', label: 'Projects' },
    { id: 'agents', label: 'Agents' },
    { id: 'memory', label: 'Memory' },
    { id: 'automation', label: 'Automation' },
    { id: 'settings', label: 'Settings' },
  ];

  const collapsedWidth = isCollapsed ? 64 : 280;
  const mainContentWidth = isCollapsed ? 'calc(100vw - 80px)' : 'calc(100vw - 280px)';

  return (
    <aside
      className={cn('w-72 h-full bg-graphite-950 border-r border-border-subtle flex-shrink-0', isCollapsed && 'r-20')}
      style={{ width: collapsedWidth }}
    >
      <div className="flex h-full flex-col">
        <header className="flex h-20 items-center justify-between px-4 pt-3">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-md bg-accent-blue flex items-center justify-center">
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                <rect x="3" y="11" width="18" height="11" rx="2" />
                <path d="M7 11V7a5 5 0 0 1 10 0v4" />
              </svg>
            </div>
            <span className={cn('text-lg font-semibold', isCollapsed && 'hidden')}>
              FRIDAY Intelligence
            </span>
          </div>
          <button onClick={onToggleCollapse} aria-label={isCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}>
            ☰
          </button>
        </header>

        <nav className="flex-1 overflow-y-auto">
          <section className="SidebarSection">Navigate</section>
          <div className="space-y-1">
            {navItems.map((item) => (
              <SidebarItem
                key={item.id}
                icon={item.icon}
                label={item.label}
                isActive={activeSection === item.id}
                onToggle={onSectionChange}
                disabled={false}
              />
            ))}
          </div>
        </nav>

        <footer className="p-4 border-t border-border-subtle">
          <div className="text-xs text-graphite-500">v0.1.0</div>
        </footer>
      </div>
    </aside>
  );
};

Sidebar.displayName = 'Sidebar';

export default Sidebar;