// Store modules for FRIDAY Intelligence
// These are architectural foundations only - no actual AI integration

import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';

export type { AIProvider, AIModel } from '../types';

// ============================================================================
// UI Store
// ============================================================================

export const useUIStore = create(
  persist(
    (set, get) => ({
      sidebar: {
        isOpen: true,
        isCollapsed: false,
        activeSection: 'conversations' as 'conversations' | 'projects' | 'agents' | 'tasks',
      },
      toggleSidebar: () =>
        set({ sidebar: { isOpen: !get().sidebar.isOpen } }),
      collapseSidebar: () => set({ sidebar: { isCollapsed: true } }),
      expandSidebar: () => set({ sidebar: { isCollapsed: false } }),
      setSidebarSection: (section: 'conversations' | 'projects' | 'agents' | 'tasks') =>
        set({ sidebar: { activeSection: section } }),
      toggleActivityPanel: () =>
        set({ sidebar: { isOpen: !get().sidebar.isOpen } }),
      setActivityTab: (tab: string) => set({ activeTab: tab }),
      addToast: (toast: any) =>
        set({ toasts: [...(get().toasts || []), toast] }),
    }),
    { name: 'friday_ui', storage: createJSONStorage(() => localStorage) }
  )
);

// ============================================================================
// Conversations Store
// ============================================================================

export const useConversationsStore = create(
  persist(
    (set) => ({
      conversations: [],
      activeConversationId: null,
      isLoading: false,
      error: null,
      createConversation: (data: any) => {
        const conv = { ...data, id: Date.now().toString(), messages: [], metadata: { messageCount: 0, totalCost: 0 }, createdAt: new Date(), updatedAt: new Date() };
        return conv;
      },
    }),
    { name: 'friday_conversations', storage: createJSONStorage(() => localStorage) }
  )
);

// ============================================================================
// Projects Store
// ============================================================================

export const useProjectsStore = create(
  persist(
    (set) => ({
      projects: [],
      activeProjectId: null,
      createProject: (data: any) => {
        const proj = { ...data, id: Date.now().toString(), createdAt: new Date(), updatedAt: new Date() };
        return proj;
      },
    }),
    { name: 'friday_projects', storage: createJSONStorage(() => localStorage) }
  )
);

// ============================================================================
// Agents Store
// ============================================================================

export const useAgentsStore = create(
  persist(
    (set) => ({
      agents: [],
      activeAgentId: null,
      createAgent: (data: any) => {
        const agent = { ...data, id: Date.now().toString(), tools: [], status: 'idle', createdAt: new Date(), updatedAt: new Date() };
        return agent;
      },
    }),
    { name: 'friday_agents', storage: createJSONStorage(() => localStorage) }
  )
);

// ============================================================================
// Tasks Store
// ============================================================================

export const useTasksStore = create(
  persist(
    (set) => ({
      tasks: [],
      activeTaskId: null,
      createTask: (data: any) => {
        const task = { ...data, id: Date.now().toString(), status: 'queued', steps: [], metadata: { tags: [], priority: 'normal' } };
        return task;
      },
      cancelTask: (id: string) => {
        // Mock cancellation - just mark as cancelled
        return { status: 'cancelled' as const };
      }
    }),
    { name: 'friday_tasks', storage: createJSONStorage(() => localStorage) }
  )
);

// ============================================================================
// System Store
// ============================================================================

export const useSystemStore = create(
  persist(
    (set) => ({
      status: {
        cpuUsage: 0,
        memoryUsage: 0,
        memoryTotal: 16 * 1024 * 1024 * 1024,
        diskUsage: 0,
        diskTotal: 512 * 1024 * 1024 * 1024,
        networkStatus: 'online',
        uptime: 0,
      },
      connections: [],
    }),
    { name: 'friday_system', storage: createJSONStorage(() => localStorage) }
  )
);