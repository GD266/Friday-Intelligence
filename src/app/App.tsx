import Layout from '@/layouts/Layout';
import { ConversationArea } from '@/components/workspace/ConversationArea';
import { useConversationsStore, useUIStore } from '@/stores';
import type { SidebarSection } from '@/types';

const sectionInfo: Record<Exclude<SidebarSection, 'conversations'>, { title: string; description: string }> = {
  projects: {
    title: 'Projects',
    description: 'Project workspaces will be configured here in a later phase.',
  },
  agents: {
    title: 'Agents',
    description: 'Agent definitions and permissions will be managed here in a later phase.',
  },
  memory: {
    title: 'Memory',
    description: 'Conversation memory and knowledge storage will be added in a later phase.',
  },
  automation: {
    title: 'Automation',
    description: 'Task automation workflows will be added in a later phase.',
  },
  settings: {
    title: 'Settings',
    description: 'Application and provider settings will be configured here in a later phase.',
  },
};

export default function App() {
  const activeSection = useUIStore((state) => state.sidebar.activeSection);
  const conversations = useConversationsStore((state) => state.conversations);
  const activeConversationId = useConversationsStore((state) => state.activeConversationId);
  const createConversation = useConversationsStore((state) => state.createConversation);
  const addMessage = useConversationsStore((state) => state.addMessage);

  const activeConversation =
    conversations.find((conversation) => conversation.id === activeConversationId) ?? null;

  const handleMessageAdded = (content: string) => {
    if (activeConversation) {
      addMessage(activeConversation.id, content);
      return;
    }

    const conversation = createConversation({
      title: content.length > 60 ? `${content.slice(0, 60)}…` : content,
    });
    addMessage(conversation.id, content);
  };

  const section = activeSection === 'conversations' ? null : sectionInfo[activeSection];

  return (
    <Layout title="FRIDAY Intelligence" subtitle="Premium AI Desktop Workspace">
      {activeSection === 'conversations' ? (
        <ConversationArea
          messages={activeConversation?.messages ?? []}
          onMessageAdded={handleMessageAdded}
        />
      ) : (
        <section className="flex h-full flex-col items-center justify-center text-center">
          <div className="max-w-md rounded-lg border border-border-subtle bg-surface-elevated p-8">
            <h2 className="text-xl font-semibold text-graphite-100">{section?.title}</h2>
            <p className="mt-2 text-sm text-graphite-400">{section?.description}</p>
          </div>
        </section>
      )}
    </Layout>
  );
}
