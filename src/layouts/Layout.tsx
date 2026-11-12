import { type ReactNode } from 'react';
import { useConversationsStore, useUIStore } from '@/stores';
import TopBar from '@/components/topbar/TopBar';
import Sidebar from '@/components/sidebar/Sidebar';
import ActivityPanel from '@/components/activity/ActivityPanel';

export interface LayoutProps {
  children?: ReactNode;
  title?: string;
  subtitle?: string;
}

export const Layout = ({ children, title, subtitle }: LayoutProps) => {
  const sidebar = useUIStore((state) => state.sidebar);
  const activityPanel = useUIStore((state) => state.activityPanel);
  const toggleSidebar = useUIStore((state) => state.toggleSidebar);
  const setSidebarSection = useUIStore((state) => state.setSidebarSection);
  const toggleActivityPanel = useUIStore((state) => state.toggleActivityPanel);
  const setActivityTab = useUIStore((state) => state.setActivityTab);
  const createConversation = useConversationsStore((state) => state.createConversation);

  const handleNewConversation = () => {
    createConversation();
    setSidebarSection('conversations');
  };

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-graphite-950 text-graphite-100">
      <TopBar
        title={title ?? 'FRIDAY Intelligence'}
        subtitle={subtitle ?? 'Premium AI Desktop Workspace'}
        onToggleSidebar={toggleSidebar}
        onToggleActivity={toggleActivityPanel}
        onOpenSettings={() => setSidebarSection('settings')}
        onNewConversation={handleNewConversation}
        showActivityPanel={activityPanel.isOpen}
      />

      <div className="flex min-h-0 flex-1">
        <Sidebar
          activeSection={sidebar.activeSection}
          onSectionChange={setSidebarSection}
          isCollapsed={sidebar.isCollapsed}
          onToggleCollapse={toggleSidebar}
        />

        <main className="min-h-0 min-w-0 flex-1 overflow-hidden p-4">{children}</main>

        <ActivityPanel
          isOpen={activityPanel.isOpen}
          activeTab={activityPanel.activeTab}
          onTabChange={setActivityTab}
          onClose={toggleActivityPanel}
          events={[]}
        />
      </div>
    </div>
  );
};

Layout.displayName = 'Layout';

export default Layout;
