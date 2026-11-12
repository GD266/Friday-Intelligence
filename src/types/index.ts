/**
 * FRIDAY Intelligence - Core Type Definitions
 * Foundation architecture for AI providers, agents, conversations, tools, and memory.
 */

// ============================================================================
// AI Provider Types
// ============================================================================

export type AIProviderId =
  | 'openai'
  | 'anthropic'
  | 'google'
  | 'ollama'
  | 'custom';

export interface AIProvider {
  id: AIProviderId;
  name: string;
  displayName: string;
  description: string;
  icon: string;
  isLocal: boolean;
  requiresApiKey: boolean;
  supportedModels: AIModel[];
  capabilities: AIProviderCapabilities;
  configSchema: AIProviderConfigSchema;
  status: AIProviderStatus;
}

export interface AIModel {
  id: string;
  name: string;
  displayName: string;
  description: string;
  providerId: AIProviderId;
  contextWindow: number;
  maxOutputTokens: number;
  capabilities: ModelCapabilities;
  pricing?: ModelPricing;
  isDefault?: boolean;
  isAvailable: boolean;
}

export interface AIProviderCapabilities {
  chatCompletion: boolean;
  streaming: boolean;
  functionCalling: boolean;
  vision: boolean;
  audioInput: boolean;
  audioOutput: boolean;
  embeddings: boolean;
  fineTuning: boolean;
}

export interface ModelCapabilities {
  reasoning: boolean;
  codeGeneration: boolean;
  analysis: boolean;
  creativeWriting: boolean;
  translation: boolean;
  summarization: boolean;
  functionCalling: boolean;
  vision: boolean;
}

export interface ModelPricing {
  inputPerMillion: number;
  outputPerMillion: number;
  currency: 'USD';
}

export interface AIProviderConfigSchema {
  apiKey?: ConfigField;
  baseUrl?: ConfigField;
  organizationId?: ConfigField;
  customHeaders?: ConfigField;
}

export interface ConfigField {
  type: 'string' | 'password' | 'url' | 'number' | 'boolean';
  label: string;
  placeholder?: string;
  required: boolean;
  description?: string;
  validation?: string;
}

export type AIProviderStatus =
  | 'disconnected'
  | 'connecting'
  | 'connected'
  | 'error'
  | 'rate-limited';

// ============================================================================
// Conversation & Message Types
// ============================================================================

export interface Conversation {
  id: string;
  title: string;
  projectId?: string;
  agentId?: string;
  modelId: string;
  providerId: AIProviderId;
  messages: Message[];
  metadata: ConversationMetadata;
  createdAt: Date;
  updatedAt: Date;
  archivedAt?: Date;
  isPinned: boolean;
}

export interface ConversationMetadata {
  messageCount: number;
  tokenCount: number;
  totalCost: number;
  tags: string[];
  summary?: string;
}

export interface Message {
  id: string;
  conversationId: string;
  role: MessageRole;
  content: MessageContent;
  metadata: MessageMetadata;
  createdAt: Date;
  updatedAt?: Date;
}

export type MessageRole = 'user' | 'assistant' | 'system' | 'tool';

export interface MessageContent {
  type: 'text' | 'image' | 'audio' | 'tool_result' | 'tool_call';
  text?: string;
  imageUrl?: string;
  audioUrl?: string;
  toolCallId?: string;
  toolName?: string;
  toolArgs?: Record<string, unknown>;
  toolResult?: ToolResult;
}

export interface MessageMetadata {
  modelId?: string;
  providerId?: AIProviderId;
  tokenCount?: {
    input: number;
    output: number;
    total: number;
  };
  cost?: number;
  latencyMs?: number;
  finishReason?: 'stop' | 'length' | 'tool_calls' | 'content_filter' | 'error';
  error?: string;
  isStreaming?: boolean;
}

// ============================================================================
// Agent Types
// ============================================================================

export interface Agent {
  id: string;
  name: string;
  displayName: string;
  description: string;
  avatar?: string;
  systemPrompt: string;
  modelId: string;
  providerId: AIProviderId;
  tools: AgentTool[];
  permissions: AgentPermissions;
  config: AgentConfig;
  status: AgentStatus;
  createdAt: Date;
  updatedAt: Date;
  lastActiveAt?: Date;
}

export interface AgentTool {
  id: string;
  name: string;
  description: string;
  parameters: ToolParameters;
  requiredPermissions: PermissionLevel[];
  isEnabled: boolean;
  handler: string; // Reference to handler function
}

export interface ToolParameters {
  type: 'object';
  properties: Record<string, ToolParameterProperty>;
  required: string[];
}

export interface ToolParameterProperty {
  type: 'string' | 'number' | 'boolean' | 'object' | 'array';
  description: string;
  enum?: string[];
  items?: ToolParameterProperty;
  properties?: Record<string, ToolParameterProperty>;
  required?: string[];
}

export type PermissionLevel =
  | 'read'
  | 'write'
  | 'execute'
  | 'network'
  | 'filesystem'
  | 'shell'
  | 'system'
  | 'admin';

export interface AgentPermissions {
  allowedTools: string[];
  deniedTools: string[];
  maxConcurrentTasks: number;
  maxExecutionTimeMs: number;
  requireConfirmationFor: PermissionLevel[];
  allowedPaths: string[];
  deniedPaths: string[];
  allowedDomains: string[];
  deniedDomains: string[];
}

export interface AgentConfig {
  temperature: number;
  topP: number;
  maxTokens: number;
  maxIterations: number;
  enableThinking: boolean;
  thinkingBudget?: number;
  responseFormat?: 'text' | 'json' | 'markdown';
  stopSequences?: string[];
}

export type AgentStatus =
  | 'idle'
  | 'initializing'
  | 'running'
  | 'paused'
  | 'completed'
  | 'error'
  | 'cancelled';

// ============================================================================
// Agent Task Types
// ============================================================================

export interface AgentTask {
  id: string;
  agentId: string;
  conversationId?: string;
  name: string;
  description: string;
  input: TaskInput;
  output?: TaskOutput;
  status: TaskStatus;
  progress: TaskProgress;
  steps: TaskStep[];
  startedAt?: Date;
  completedAt?: Date;
  cancelledAt?: Date;
  error?: TaskError;
  metadata: TaskMetadata;
}

export interface TaskInput {
  prompt: string;
  context?: Record<string, unknown>;
  files?: TaskFile[];
  parameters?: Record<string, unknown>;
}

export interface TaskOutput {
  result: unknown;
  summary: string;
  artifacts: TaskArtifact[];
  metrics: TaskMetrics;
}

export interface TaskFile {
  id: string;
  name: string;
  path: string;
  mimeType: string;
  size: number;
  content?: string;
}

export interface TaskArtifact {
  id: string;
  name: string;
  type: 'file' | 'code' | 'text' | 'image' | 'data';
  content: string;
  path?: string;
  mimeType?: string;
}

export interface TaskMetrics {
  durationMs: number;
  tokenCount: {
    input: number;
    output: number;
    total: number;
  };
  toolCalls: number;
  iterations: number;
  cost: number;
}

export interface TaskProgress {
  currentStep: number;
  totalSteps: number;
  percentComplete: number;
  currentOperation: string;
}

export interface TaskStep {
  id: string;
  name: string;
  description: string;
  status: TaskStepStatus;
  toolCall?: ToolCall;
  toolResult?: ToolResult;
  startedAt?: Date;
  completedAt?: Date;
  error?: string;
}

export type TaskStepStatus =
  | 'pending'
  | 'running'
  | 'completed'
  | 'failed'
  | 'skipped';

export interface ToolCall {
  id: string;
  name: string;
  arguments: Record<string, unknown>;
  requestId: string;
}

export interface ToolResult {
  id: string;
  toolCallId: string;
  success: boolean;
  output?: unknown;
  error?: ToolError;
  durationMs: number;
  metadata?: Record<string, unknown>;
}

export interface ToolError {
  code: string;
  message: string;
  details?: unknown;
  recoverable: boolean;
}

export interface TaskError {
  code: string;
  message: string;
  stepId?: string;
  recoverable: boolean;
  retryCount: number;
}

export type TaskStatus =
  | 'queued'
  | 'initializing'
  | 'running'
  | 'paused'
  | 'waiting_confirmation'
  | 'completed'
  | 'failed'
  | 'cancelled'
  | 'timeout';

export interface TaskMetadata {
  parentTaskId?: string;
  tags: string[];
  priority: 'low' | 'normal' | 'high' | 'critical';
  retryPolicy?: RetryPolicy;
}

export interface RetryPolicy {
  maxRetries: number;
  baseDelayMs: number;
  maxDelayMs: number;
  backoffMultiplier: number;
  retryableErrors: string[];
}

// ============================================================================
// Tool Types
// ============================================================================

export interface Tool {
  id: string;
  name: string;
  displayName: string;
  description: string;
  category: ToolCategory;
  version: string;
  author: string;
  parameters: ToolParameters;
  returns: ToolReturnSchema;
  permissions: PermissionLevel[];
  isBuiltIn: boolean;
  isEnabled: boolean;
  configSchema?: ToolConfigSchema;
  handler: string;
}

export type ToolCategory =
  | 'filesystem'
  | 'shell'
  | 'network'
  | 'code'
  | 'data'
  | 'web'
  | 'system'
  | 'custom';

export interface ToolReturnSchema {
  type: 'object' | 'string' | 'number' | 'boolean' | 'array';
  properties?: Record<string, ToolReturnProperty>;
  description: string;
}

export interface ToolReturnProperty {
  type: string;
  description: string;
}

export interface ToolConfigSchema {
  properties: Record<string, ConfigField>;
  required: string[];
}

// ============================================================================
// Activity & Event Types
// ============================================================================

export interface ActivityEvent {
  id: string;
  type: ActivityEventType;
  timestamp: Date;
  agentId?: string;
  conversationId?: string;
  taskId?: string;
  toolId?: string;
  title: string;
  description: string;
  level: ActivityLevel;
  metadata: Record<string, unknown>;
  durationMs?: number;
  status: ActivityStatus;
}

export type ActivityEventType =
  | 'agent_started'
  | 'agent_completed'
  | 'agent_failed'
  | 'agent_cancelled'
  | 'task_started'
  | 'task_step_started'
  | 'task_step_completed'
  | 'task_step_failed'
  | 'task_completed'
  | 'task_failed'
  | 'tool_invoked'
  | 'tool_completed'
  | 'tool_failed'
  | 'permission_requested'
  | 'permission_granted'
  | 'permission_denied'
  | 'conversation_created'
  | 'message_sent'
  | 'message_received'
  | 'model_switched'
  | 'settings_changed'
  | 'error'
  | 'warning'
  | 'info';

export type ActivityLevel = 'debug' | 'info' | 'warning' | 'error' | 'critical';

export type ActivityStatus =
  | 'pending'
  | 'running'
  | 'success'
  | 'failed'
  | 'cancelled';

// ============================================================================
// Memory Types
// ============================================================================

export interface MemoryEntry {
  id: string;
  type: MemoryType;
  scope: MemoryScope;
  key: string;
  value: unknown;
  metadata: MemoryMetadata;
  createdAt: Date;
  updatedAt: Date;
  expiresAt?: Date;
  accessCount: number;
  lastAccessedAt: Date;
}

export type MemoryType =
  | 'fact'
  | 'preference'
  | 'context'
  | 'procedure'
  | 'conversation_summary'
  | 'entity'
  | 'relationship'
  | 'skill';

export type MemoryScope =
  | 'global'
  | 'project'
  | 'conversation'
  | 'agent'
  | 'user';

export interface MemoryMetadata {
  source: 'user' | 'agent' | 'system' | 'imported';
  confidence: number;
  tags: string[];
  relatedEntries: string[];
  version: number;
}

// ============================================================================
// Project Types
// ============================================================================

export interface Project {
  id: string;
  name: string;
  displayName: string;
  description: string;
  path: string;
  icon?: string;
  color?: string;
  agents: string[];
  conversations: string[];
  settings: ProjectSettings;
  createdAt: Date;
  updatedAt: Date;
  lastOpenedAt?: Date;
}

export interface ProjectSettings {
  defaultModelId?: string;
  defaultAgentId?: string;
  allowedTools: string[];
  environmentVariables: Record<string, string>;
  workingDirectory: string;
}

// ============================================================================
// Settings Types
// ============================================================================

export interface AppSettings {
  appearance: AppearanceSettings;
  aiProviders: AIProviderSettings;
  agents: AgentSettings;
  privacy: PrivacySettings;
  advanced: AdvancedSettings;
  shortcuts: ShortcutSettings;
}

export interface AppearanceSettings {
  theme: 'system' | 'dark' | 'light';
  accentColor: 'blue' | 'violet' | 'emerald' | 'amber';
  density: 'compact' | 'comfortable' | 'spacious';
  animations: boolean;
  reducedMotion: boolean;
  fontSize: number;
  fontFamily: string;
}

export interface AIProviderSettings {
  providers: Record<AIProviderId, ProviderSettings>;
  defaultProvider: AIProviderId;
  defaultModel: string;
  fallbackModel?: string;
}

export interface ProviderSettings {
  enabled: boolean;
  apiKey?: string;
  baseUrl?: string;
  organizationId?: string;
  customHeaders?: Record<string, string>;
  models: Record<string, ModelSettings>;
}

export interface ModelSettings {
  enabled: boolean;
  temperature?: number;
  topP?: number;
  maxTokens?: number;
}

export interface AgentSettings {
  defaultPermissions: AgentPermissions;
  maxConcurrentAgents: number;
  defaultModelId: string;
  autoSaveConversations: boolean;
  conversationRetentionDays: number;
}

export interface PrivacySettings {
  telemetryEnabled: boolean;
  crashReportingEnabled: boolean;
  dataCollectionConsent: boolean;
  localOnlyMode: boolean;
  encryptLocalData: boolean;
}

export interface AdvancedSettings {
  logLevel: 'debug' | 'info' | 'warn' | 'error';
  maxLogSizeMb: number;
  enableDevTools: boolean;
  experimentalFeatures: boolean;
  customCssPath?: string;
}

export interface ShortcutSettings {
  globalShortcuts: Record<string, string>;
  appShortcuts: Record<string, string>;
}

// ============================================================================
// System Status Types
// ============================================================================

export interface SystemStatus {
  cpuUsage: number;
  memoryUsage: number;
  memoryTotal: number;
  diskUsage: number;
  diskTotal: number;
  networkStatus: 'online' | 'offline' | 'limited';
  uptime: number;
  version: string;
  tauriVersion: string;
  platform: string;
  arch: string;
}

export interface ConnectionStatus {
  providerId: AIProviderId;
  status: AIProviderStatus;
  latencyMs?: number;
  lastCheck: Date;
  error?: string;
}

// ============================================================================
// UI State Types
// ============================================================================

export interface UIState {
  sidebar: SidebarState;
  activityPanel: ActivityPanelState;
  modals: ModalState[];
  toasts: ToastState[];
  commandPalette: CommandPaletteState;
}

export interface SidebarState {
  isOpen: boolean;
  isCollapsed: boolean;
  activeSection: SidebarSection;
  width: number;
}

export type SidebarSection =
  | 'conversations'
  | 'projects'
  | 'agents'
  | 'memory'
  | 'automation'
  | 'settings';

export interface ActivityPanelState {
  isOpen: boolean;
  width: number;
  activeTab: ActivityTab;
}

export type ActivityTab =
  | 'agents'
  | 'tasks'
  | 'tools'
  | 'system'
  | 'logs';

export interface ModalState {
  id: string;
  type: ModalType;
  title: string;
  content: React.ReactNode;
  size: 'sm' | 'md' | 'lg' | 'xl' | 'full';
  isOpen: boolean;
  onClose: () => void;
}

export type ModalType =
  | 'confirm'
  | 'settings'
  | 'new-conversation'
  | 'new-project'
  | 'new-agent'
  | 'provider-config'
  | 'permissions'
  | 'about';

export interface ToastState {
  id: string;
  type: 'success' | 'error' | 'warning' | 'info';
  title: string;
  message?: string;
  duration?: number;
  action?: ToastAction;
}

export interface ToastAction {
  label: string;
  onClick: () => void;
}

export interface CommandPaletteState {
  isOpen: boolean;
  query: string;
  selectedIndex: number;
  results: CommandResult[];
}

export interface CommandResult {
  id: string;
  title: string;
  description?: string;
  icon?: string;
  category: string;
  keywords: string[];
  action: () => void;
}