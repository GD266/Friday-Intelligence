// Store modules for FRIDAY Intelligence
// Phase 1 foundation: local state only, no AI provider integration.

import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';
import { generateId } from '../lib/utils';
import type {
  Agent,
  AgentConfig,
  AgentPermissions,
  AgentTask,
  AutomationLogEntry,
  ConnectionStatus,
  Conversation,
  CoreOverlay,
  DeveloperProject,
  DeveloperTask,
  EngineStatus,
  FridayMood,
  FridaySettings,
  Message,
  MessageMetadata,
  MessageRole,
  PendingAutomation,
  Project,
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
  overlay: CoreOverlay | null;
  toasts: ToastState[];
  isCommandPaletteOpen: boolean;
  openOverlay: (overlay: CoreOverlay) => void;
  closeOverlay: () => void;
  addToast: (toast: Omit<ToastState, 'id'> & { id?: string }) => void;
  removeToast: (id: string) => void;
  setCommandPaletteOpen: (open: boolean) => void;
  toggleCommandPalette: () => void;
}

export const useUIStore = create<UIStore>((set) => ({
  overlay: null,
  toasts: [],
  isCommandPaletteOpen: false,
  openOverlay: (overlay) => set({ overlay, isCommandPaletteOpen: false }),
  closeOverlay: () => set({ overlay: null }),
  addToast: (toast) =>
    set((state) => ({
      toasts: [...state.toasts, { ...toast, id: toast.id ?? generateId('toast') }],
    })),
  removeToast: (id) =>
    set((state) => ({ toasts: state.toasts.filter((toast) => toast.id !== id) })),
  setCommandPaletteOpen: (open) => set({ isCommandPaletteOpen: open }),
  toggleCommandPalette: () =>
    set((state) => ({ isCommandPaletteOpen: !state.isCommandPaletteOpen })),
}));

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
  renameConversation: (id: string, title: string) => void;
  addMessage: (
    conversationId: string,
    content: string,
    role?: MessageRole,
    metadata?: MessageMetadata
  ) => Message | null;
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
          modelId: data.modelId ?? 'friday-core-demo',
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
      renameConversation: (id, title) =>
        set((state) => ({
          conversations: state.conversations.map((conversation) =>
            conversation.id === id ? { ...conversation, title, updatedAt: new Date() } : conversation
          ),
        })),
      addMessage: (conversationId, content, role = 'user', metadata = {}) => {
        const conversation = get().conversations.find((item) => item.id === conversationId);
        if (!conversation) return null;

        const now = new Date();
        const message: Message = {
          id: generateId('message'),
          conversationId,
          role,
          content: { type: 'text', text: content },
          metadata,
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
  setStatus: (status: Partial<SystemStatus>) => void;
  setConnections: (connections: ConnectionStatus[]) => void;
}

const initialSystemStatus: SystemStatus = {
  cpuUsage: 0,
  memoryUsage: 0,
  memoryTotal: 16 * 1024 * 1024 * 1024,
  diskUsage: 0,
  diskTotal: 512 * 1024 * 1024 * 1024,
  networkStatus: 'online',
  uptime: 0,
  version: '0.2.0',
  tauriVersion: '2',
  platform: typeof navigator !== 'undefined' ? navigator.platform : 'unknown',
  arch: 'unknown',
};

export const useSystemStore = create<SystemStore>()(
  persist(
    (set) => ({
      status: initialSystemStatus,
      connections: [] as ConnectionStatus[],
      setStatus: (status) =>
        set((state) => ({ status: { ...state.status, ...status } })),
      setConnections: (connections) => set({ connections }),
    }),
    {
      name: 'friday_system',
      storage: createStorage(),
      partialize: (state) => ({ status: state.status }),
    }
  )
);

// ============================================================================
// FRIDAY Assistant Store
// ============================================================================

export const DEFAULT_FRIDAY_SETTINGS: FridaySettings = {
  addressAs: 'sir',
  userName: '',
  voiceEnabled: true,
  autoSpeak: true,
  voiceRate: 0.96,
  voicePitch: 1,
  voiceId: null,
  soundEffects: true,
  requireConfirmation: true,
  demoMode: false,
  voiceLocale: 'en-IN',

  // STT defaults: local Whisper (no key, offline).
  sttProvider: 'local',
  sttModel: 'small.en',
  groqApiKey: '',

  // TTS defaults: Edge neural voices (no key, free).
  ttsProvider: 'edge',
  ttsVoice: 'en-IN-NeerjaExpressiveNeural',

  engineProvider: 'auto',
  engineModel: 'opencode/nemotron-3.5-lightning-free',
  openCodeApiKey: '',
  nvidiaApiKey: '',
  openRouterApiKey: '',
  engineTemperature: 0.65,
  engineMaxTokens: 1400,

  voiceProvider: 'auto',
  elevenLabsApiKey: '',
  elevenLabsVoiceId: '21m00Tcm4TlvDq8ikWAM',
  elevenLabsModelId: 'eleven_turbo_v2_5',
  elevenLabsStability: 0.45,
  elevenLabsSimilarity: 0.75,

  developerAutoOpen: true,
};

export const DEFAULT_ENGINE_STATUS: EngineStatus = {
  state: 'idle',
  source: 'demo',
  model: 'Local demo core',
};

interface AssistantStore {
  settings: FridaySettings;
  mood: FridayMood;
  statusText: string;
  isListening: boolean;
  isSpeaking: boolean;
  audioLevel: number;
  transcript: string;
  pendingAutomation: PendingAutomation | null;
  automationLog: AutomationLogEntry[];
  lastReply: string | null;
  engineStatus: EngineStatus;
  developerTask: DeveloperTask | null;
  developerProjects: DeveloperProject[];
  updateSettings: (settings: Partial<FridaySettings>) => void;
  resetSettings: () => void;
  setMood: (mood: FridayMood) => void;
  setStatusText: (statusText: string) => void;
  setListening: (isListening: boolean) => void;
  setSpeaking: (isSpeaking: boolean) => void;
  setAudioLevel: (audioLevel: number) => void;
  setTranscript: (transcript: string) => void;
  requestAutomation: (pending: PendingAutomation) => void;
  clearPendingAutomation: () => void;
  addAutomationLog: (entry: AutomationLogEntry) => void;
  updateAutomationLog: (id: string, update: Partial<AutomationLogEntry>) => void;
  clearAutomationLog: () => void;
  setLastReply: (lastReply: string | null) => void;
  setEngineStatus: (status: Partial<EngineStatus>) => void;
  setDeveloperTask: (task: DeveloperTask | null) => void;
  updateDeveloperTask: (update: Partial<DeveloperTask>) => void;
  addDeveloperProject: (project: DeveloperProject) => void;
}

export const useAssistantStore = create<AssistantStore>()(
  persist(
    (set) => ({
      settings: DEFAULT_FRIDAY_SETTINGS,
      mood: 'idle',
      statusText: 'Online',
      isListening: false,
      isSpeaking: false,
      audioLevel: 0,
      transcript: '',
      pendingAutomation: null,
      automationLog: [],
      lastReply: null,
      engineStatus: DEFAULT_ENGINE_STATUS,
      developerTask: null,
      developerProjects: [],
      updateSettings: (settings) =>
        set((state) => ({ settings: { ...state.settings, ...settings } })),
      resetSettings: () => set({ settings: DEFAULT_FRIDAY_SETTINGS }),
      setMood: (mood) => set({ mood }),
      setStatusText: (statusText) => set({ statusText }),
      setListening: (isListening) => set({ isListening }),
      setSpeaking: (isSpeaking) => set({ isSpeaking }),
      setAudioLevel: (audioLevel) => set({ audioLevel }),
      setTranscript: (transcript) => set({ transcript }),
      requestAutomation: (pendingAutomation) => set({ pendingAutomation }),
      clearPendingAutomation: () => set({ pendingAutomation: null }),
      addAutomationLog: (entry) =>
        set((state) => ({ automationLog: [entry, ...state.automationLog].slice(0, 100) })),
      updateAutomationLog: (id, update) =>
        set((state) => ({
          automationLog: state.automationLog.map((entry) =>
            entry.id === id ? { ...entry, ...update } : entry
          ),
        })),
      clearAutomationLog: () => set({ automationLog: [] }),
      setLastReply: (lastReply) => set({ lastReply }),
      setEngineStatus: (status) =>
        set((state) => ({
          engineStatus: { ...state.engineStatus, ...status, checkedAt: status.checkedAt ?? new Date() },
        })),
      setDeveloperTask: (developerTask) => set({ developerTask }),
      updateDeveloperTask: (update) =>
        set((state) =>
          state.developerTask ? { developerTask: { ...state.developerTask, ...update } } : state
        ),
      addDeveloperProject: (project) =>
        set((state) => ({
          developerProjects: [project, ...state.developerProjects].slice(0, 24),
        })),
    }),
    {
      name: 'friday_assistant',
      storage: createStorage(),
      version: 4,
      migrate: (persistedState, version) => {
        const state = persistedState as Partial<AssistantStore> | undefined;
        if (!state?.settings) return state as AssistantStore;

        // Phase 2 shipped a lower, more masculine pitch. Only upgrade untouched
        // legacy defaults so a user's deliberate tuning is preserved.
        const isLegacyDefault =
          state.settings.voicePitch === 0.85 && state.settings.voiceRate === 0.95;

        return {
          ...state,
          developerProjects: state.developerProjects ?? [],
          settings: {
            ...DEFAULT_FRIDAY_SETTINGS,
            ...state.settings,
            ...(version < 2 && isLegacyDefault
              ? {
                  voicePitch: DEFAULT_FRIDAY_SETTINGS.voicePitch,
                  voiceRate: DEFAULT_FRIDAY_SETTINGS.voiceRate,
                }
              : {}),
            // Demo-only was the old default and there was no toggle to opt into
            // it. New installs should try the engine, then fall back safely.
            ...(version < 3 ? { demoMode: false } : {}),
            // Phase 4: new STT/TTS provider fields with safe defaults.
            ...(version < 4
              ? {
                  sttProvider: 'local',
                  sttModel: 'small.en',
                  groqApiKey: '',
                  ttsProvider: 'edge',
                  ttsVoice: 'en-IN-NeerjaExpressiveNeural',
                }
              : {}),
          },
        } as AssistantStore;
      },
      partialize: (state) => ({
        settings: state.settings,
        automationLog: state.automationLog,
        developerProjects: state.developerProjects,
      }),
    }
  )
);
