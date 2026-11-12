// Store modules for FRIDAY Intelligence
// Phase 1 foundation: local state only, no AI provider integration.

import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';
import { generateId } from '../lib/utils';
import type {
  ActivityPanelState,
  ActivityTab,
  Agent,
  AgentConfig,
  AgentPermissions,
  AgentTask,
  ConnectionStatus,
  Conversation,
  Message,
  Project,
  SidebarSection,
  SidebarState,
  SystemStatus,
  ToastState,
} from '../types';

export type { AIProvider, AIModel } from '../types';

const ISO_DATE = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$/;

const dateReviver = (_key: string, value: unknown): unknown =>
  typeof value === 'string' && ISO_DATE.test(value) ? new Date(value) : value;

const createStorage = () => createJSONStorage(() => localStorage, { reviver: dateReviver });

// ============================================================================
// UI Store
// ============================================================================

interface UIStore {
  sidebar: SidebarState;
  activityPanel: ActivityPanelState;
  toasts: ToastState[];
  toggleSidebar: () => void;
  collapseSidebar: () => void;
  expandSidebar: () => void;
  setSidebarSection: (section: SidebarSection) => void;
  toggleActivityPanel: () => void;
  setActivityTab: (tab: ActivityTab) => void;
  addToast: (toast: Omit<ToastState, 'id'> & { id?: string }) => void;
  removeToast: (id: string) => void;
}

export const useUIStore = create<UIStore>()(
  persist(
    (set) => ({
      sidebar: {
        isOpen: true,
        isCollapsed: false,
        activeSection: 'conversations',
        width: 280,
      },
      activityPanel: {
        isOpen: false,
        width: 320,
        activeTab: 'agents',
      },
      toasts: [],
      toggleSidebar: () =>
        set((state) => ({
          sidebar: { ...state.sidebar, isCollapsed: !state.sidebar.isCollapsed },
        })),
      collapseSidebar: () =>
        set((state) => ({ sidebar: { ...state.sidebar, isCollapsed: true } })),
      expandSidebar: () =>
        set((state) => ({ sidebar: { ...state.sidebar, isCollapsed: false } })),
      setSidebarSection: (section) =>
        set((state) => ({ sidebar: { ...state.sidebar, activeSection: section } })),
      toggleActivityPanel: () =>
        set((state) => ({
          activityPanel: { ...state.activityPanel, isOpen: !state.activityPanel.isOpen },
        })),
      setActivityTab: (tab) =>
        set((state) => ({ activityPanel: { ...state.activityPanel, activeTab: tab } })),
      addToast: (toast) =>
        set((state) => ({
          toasts: [...state.toasts, { ...toast, id: toast.id ?? generateId('toast') }],
        })),
      removeToast: (id) =>
        set((state) => ({ toasts: state.toasts.filter((toast) => toast.id !== id) })),
    }),
    { name: 'friday_ui', storage: createStorage() }
  )
);

// ============================================================================
// Conversations Store
// ============================================================================

interface ConversationsStore {
  conversations: Conversation[];
  activeConversationId: string | null;
  isLoading: boolean;
  error: string | null;
  createConversation: (data?: Partial<Conversation>) => Conversation;
  setActiveConversation: (id: string | null) => void;
  addMessage: (conversationId: string, content: string) => Message | null;
}

export const useConversationsStore = create<ConversationsStore>()(
  persist(
    (set, get) => ({
      conversations: [],
      activeConversationId: null,
      isLoading: false,
      error: null,
      createConversation: (data = {}) => {
        const now = new Date();
        const conversation: Conversation = {
          id: generateId('conversation'),
          title: data.title ?? 'New conversation',
          projectId: data.projectId,
          agentId: data.agentId,
          modelId: data.modelId ?? 'unconfigured',
          providerId: data.providerId ?? 'custom',
          messages: data.messages ?? [],
          metadata: data.metadata ?? {
            messageCount: 0,
            tokenCount: 0,
            totalCost: 0,
            tags: [],
          },
          createdAt: data.createdAt ?? now,
          updatedAt: data.updatedAt ?? now,
          archivedAt: data.archivedAt,
          isPinned: data.isPinned ?? false,
        };

        set((state) => ({
          conversations: [conversation, ...state.conversations],
          activeConversationId: conversation.id,
        }));

        return conversation;
      },
      setActiveConversation: (id) => set({ activeConversationId: id }),
      addMessage: (conversationId, content) => {
        const conversation = get().conversations.find((item) => item.id === conversationId);
        if (!conversation) return null;

        const now = new Date();
        const message: Message = {
          id: generateId('message'),
          conversationId,
          role: 'user',
          content: { type: 'text', text: content },
          metadata: {},
          createdAt: now,
        };

        set((state) => ({
          conversations: state.conversations.map((item) =>
            item.id === conversationId
              ? {
                  ...item,
                  messages: [...item.messages, message],
                  metadata: {
                    ...item.metadata,
                    messageCount: item.metadata.messageCount + 1,
                  },
                  updatedAt: now,
                }
              : item
          ),
        }));

        return message;
      },
    }),
    { name: 'friday_conversations', storage: createStorage() }
  )
);

// ============================================================================
// Projects Store
// ============================================================================

interface ProjectsStore {
  projects: Project[];
  activeProjectId: string | null;
  createProject: (data?: Partial<Project>) => Project;
  setActiveProject: (id: string | null) => void;
}

export const useProjectsStore = create<ProjectsStore>()(
  persist(
    (set) => ({
      projects: [],
      activeProjectId: null,
      createProject: (data = {}) => {
        const now = new Date();
        const project: Project = {
          id: generateId('project'),
          name: data.name ?? 'new-project',
          displayName: data.displayName ?? data.name ?? 'New project',
          description: data.description ?? '',
          path: data.path ?? '',
          icon: data.icon,
          color: data.color,
          agents: data.agents ?? [],
          conversations: data.conversations ?? [],
          settings: data.settings ?? {
            allowedTools: [],
            environmentVariables: {},
            workingDirectory: data.path ?? '',
          },
          createdAt: data.createdAt ?? now,
          updatedAt: data.updatedAt ?? now,
          lastOpenedAt: data.lastOpenedAt,
        };

        set((state) => ({
          projects: [project, ...state.projects],
          activeProjectId: project.id,
        }));

        return project;
      },
      setActiveProject: (id) => set({ activeProjectId: id }),
    }),
    { name: 'friday_projects', storage: createStorage() }
  )
);

// ============================================================================
// Agents Store
// ============================================================================

const DEFAULT_AGENT_PERMISSIONS: AgentPermissions = {
  allowedTools: [],
  deniedTools: [],
  maxConcurrentTasks: 1,
  maxExecutionTimeMs: 300_000,
  requireConfirmationFor: [],
  allowedPaths: [],
  deniedPaths: [],
  allowedDomains: [],
  deniedDomains: [],
};

const DEFAULT_AGENT_CONFIG: AgentConfig = {
  temperature: 0.7,
  topP: 1,
  maxTokens: 4096,
  maxIterations: 10,
  enableThinking: false,
};

interface AgentsStore {
  agents: Agent[];
  activeAgentId: string | null;
  createAgent: (data?: Partial<Agent>) => Agent;
  setActiveAgent: (id: string | null) => void;
}

export const useAgentsStore = create<AgentsStore>()(
  persist(
    (set) => ({
      agents: [],
      activeAgentId: null,
      createAgent: (data = {}) => {
        const now = new Date();
        const agent: Agent = {
          id: generateId('agent'),
          name: data.name ?? 'new-agent',
          displayName: data.displayName ?? data.name ?? 'New agent',
          description: data.description ?? '',
          avatar: data.avatar,
          systemPrompt: data.systemPrompt ?? '',
          modelId: data.modelId ?? 'unconfigured',
          providerId: data.providerId ?? 'custom',
          tools: data.tools ?? [],
          permissions: data.permissions ?? DEFAULT_AGENT_PERMISSIONS,
          config: data.config ?? DEFAULT_AGENT_CONFIG,
          status: data.status ?? 'idle',
          createdAt: data.createdAt ?? now,
          updatedAt: data.updatedAt ?? now,
          lastActiveAt: data.lastActiveAt,
        };

        set((state) => ({
          agents: [agent, ...state.agents],
          activeAgentId: agent.id,
        }));

        return agent;
      },
      setActiveAgent: (id) => set({ activeAgentId: id }),
    }),
    { name: 'friday_agents', storage: createStorage() }
  )
);

// ============================================================================
// Tasks Store
// ============================================================================

interface TasksStore {
  tasks: AgentTask[];
  activeTaskId: string | null;
  createTask: (data?: Partial<AgentTask>) => AgentTask;
  cancelTask: (id: string) => void;
  setActiveTask: (id: string | null) => void;
}

export const useTasksStore = create<TasksStore>()(
  persist(
    (set) => ({
      tasks: [],
      activeTaskId: null,
      createTask: (data = {}) => {
        const task: AgentTask = {
          id: generateId('task'),
          agentId: data.agentId ?? '',
          conversationId: data.conversationId,
          name: data.name ?? 'New task',
          description: data.description ?? '',
          input: data.input ?? { prompt: '' },
          output: data.output,
          status: data.status ?? 'queued',
          progress: data.progress ?? {
            currentStep: 0,
            totalSteps: 0,
            percentComplete: 0,
            currentOperation: '',
          },
          steps: data.steps ?? [],
          startedAt: data.startedAt,
          completedAt: data.completedAt,
          cancelledAt: data.cancelledAt,
          error: data.error,
          metadata: data.metadata ?? { tags: [], priority: 'normal' },
        };

        set((state) => ({
          tasks: [task, ...state.tasks],
          activeTaskId: task.id,
        }));

        return task;
      },
      cancelTask: (id) =>
        set((state) => ({
          tasks: state.tasks.map((task) =>
            task.id === id
              ? { ...task, status: 'cancelled', cancelledAt: new Date() }
              : task
          ),
          activeTaskId: state.activeTaskId === id ? null : state.activeTaskId,
        })),
      setActiveTask: (id) => set({ activeTaskId: id }),
    }),
    { name: 'friday_tasks', storage: createStorage() }
  )
);

// ============================================================================
// System Store
// ============================================================================

interface SystemStore {
  status: SystemStatus;
  connections: ConnectionStatus[];
}

const initialSystemStatus: SystemStatus = {
  cpuUsage: 0,
  memoryUsage: 0,
  memoryTotal: 16 * 1024 * 1024 * 1024,
  diskUsage: 0,
  diskTotal: 512 * 1024 * 1024 * 1024,
  networkStatus: 'online',
  uptime: 0,
  version: '0.1.0',
  tauriVersion: '2',
  platform: typeof navigator !== 'undefined' ? navigator.platform : 'unknown',
  arch: 'unknown',
};

export const useSystemStore = create<SystemStore>()(
  persist(
    () => ({
      status: initialSystemStatus,
      connections: [] as ConnectionStatus[],
    }),
    { name: 'friday_system', storage: createStorage() }
  )
);
