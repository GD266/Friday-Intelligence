import { type ReactNode } from 'react';
import { useUIStore } from '@/stores';
import { cn } from '@/lib/utils';
import TopBar from '../topbar/TopBar';
import Sidebar from '../sidebar/Sidebar';
import ActivityPanel from '../activity/ActivityPanel';
import { useEffect } from 'react';

export interface LayoutProps {
  children?: ReactNode;
  title?: string;
  subtitle?: string;
  showActivityPanel?: boolean;
}

export const Layout = ({ children, title, subtitle, showActivityPanel = false }: LayoutProps) => {
  const {
    sidebar,
    toggleSidebar,
    collapseSidebar,
    expandSidebar,
    setSidebarSection,
    toggleActivityPanel,
    setActivityTab,
    addToast,
  } = useUIStore();

  useEffect(() => {
    // Initialize connection check
    const loadStore = document.getElementById('friday-load-store') as HTMLDivElement | null;
    if (loadStore) {
      // Store is already initialized via script
    }
  }, []);

  const mainContentWidth = sidebar.isCollapsed ? 'calc(100vw - 80px)' : 'calc(100vw - 280px)';

  return (
    <div className="min-h-screen flex flex-col">
      {/* Top Bar */}
      <TopBar
        title={title || 'FRIDAY Intelligence'}
        subtitle={subtitle || 'Premium AI Desktop Workspace'}
        onToggleSidebar={toggleSidebar}
        onToggleActivity={toggleActivityPanel}
        isConnected={sidebar.isOpen} // Mock: connected when sidebar is open
        currentModel={sidebar.activeSection}
        showActivityPanel={showActivityPanel || sidebar.isOpen}
      />

      {/* Main Content */}
      <div className="flex flex-1">
        {/* Sidebar */}
        <Sidebar
          activeSection={sidebar.activeSection}
          onSectionChange={setSidebarSection}
          isCollapsed={sidebar.isCollapsed}
          onToggleCollapse={toggleSidebar}
        />

        {/* Main Workspace */}
        <main
          className={cn(
            'flex-1 w-full overflow-auto p-4',
            !sidebar.isCollapsed && 'pl-4',
            !sidebar.isCollapsed && 'pr-4'
          )}
          style={{ width: mainContentWidth }}
        >
          {children}
        </main>
      </div>

      {/* Activity Panel */}
      <ActivityPanel
        isOpen={sidebar.isOpen}
        onToggle={toggleActivityPanel}
        events={[]}
        onEventSelect={() => {}}
      />
    </div>
  );
};

Layout.displayName = 'Layout';

export default Layout;