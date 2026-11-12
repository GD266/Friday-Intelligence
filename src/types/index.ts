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
  | 'opencode'
  | 'nvidia'
  | 'openrouter'
  | 'groq'
  | 'local'
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
  source?: 'opencode-auth' | 'environment' | 'settings' | 'fallback';
  error?: string;
  tokenCount?: {
    input: number;
    output: number;
    total: number;
  };
  cost?: number;
  latencyMs?: number;
  finishReason?: 'stop' | 'length' | 'tool_calls' | 'content_filter' | 'error';
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
  hostname?: string;
  os?: string;
  cpuName?: string;
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
  overlay: CoreOverlay | null;
  modals: ModalState[];
  toasts: ToastState[];
  commandPalette: CommandPaletteState;
}

export type CoreOverlay = 'settings' | 'automation' | 'log' | 'forge';

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

// ============================================================================
// FRIDAY Assistant, Voice & Automation Types
// ============================================================================

export type FridayMood = 'idle' | 'listening' | 'thinking' | 'speaking' | 'alert';

export interface FridaySettings {
  addressAs: 'sir' | 'name';
  userName: string;
  voiceEnabled: boolean;
  autoSpeak: boolean;
  voiceRate: number;
  voicePitch: number;
  voiceId: string | null;
  soundEffects: boolean;
  requireConfirmation: boolean;
  demoMode: boolean;

  // Voice recognition locale.
  voiceLocale: string;

  // Speech-to-text provider.
  sttProvider: 'local' | 'groq' | 'native';
  sttModel: string;
  groqApiKey: string;

  // Text-to-speech provider.
  ttsProvider: 'edge' | 'elevenlabs' | 'native';
  ttsVoice: string;

  // Intelligence engine. API keys stay in local storage on this workstation.
  engineProvider: EngineProvider | 'auto';
  engineModel: string;
  openCodeApiKey: string;
  nvidiaApiKey: string;
  openRouterApiKey: string;
  engineTemperature: number;
  engineMaxTokens: number;

  // Realistic speech through ElevenLabs, with a native fallback.
  voiceProvider: 'auto' | 'elevenlabs' | 'native';
  elevenLabsApiKey: string;
  elevenLabsVoiceId: string;
  elevenLabsModelId: string;
  elevenLabsStability: number;
  elevenLabsSimilarity: number;

  // Project forge.
  developerAutoOpen: boolean;
}

export type AutomationRisk = 'low' | 'medium' | 'high';

export type AutomationCategory =
  | 'apps'
  | 'folders'
  | 'system'
  | 'media'
  | 'window'
  | 'input'
  | 'web'
  | 'info';

export interface AutomationAction {
  id: string;
  label: string;
  description: string;
  category: AutomationCategory;
  risk: AutomationRisk;
  keywords: string[];
  requiresConfirmation: boolean;
  argumentLabel?: string;
}

export interface AutomationResult {
  success: boolean;
  message: string;
  action: string;
}

export type AutomationStatus = 'pending' | 'running' | 'success' | 'failed' | 'cancelled';

export interface AutomationLogEntry {
  id: string;
  actionId: string;
  label: string;
  risk: AutomationRisk;
  status: AutomationStatus;
  message: string;
  timestamp: Date;
  durationMs?: number;
}

export interface PendingAutomation {
  action: AutomationAction;
  argument?: string;
  requestedBy: 'text' | 'voice' | 'command-palette' | 'automation-page';
}

export interface EdgeVoice {
  shortName: string;
  locale: string;
  gender: string;
  friendlyName: string;
  recommended: boolean;
}

export interface VoiceOption {
  id: string;
  name: string;
  language: string;
  provider?: 'native' | 'elevenlabs' | 'edge';
  description?: string;
}

export type SpeechEventKind = 'started' | 'transcript' | 'audioLevel' | 'stopped' | 'error';

export interface SpeechEventPayload {
  kind: SpeechEventKind;
  text?: string;
  isFinal?: boolean;
  level?: number;
  message?: string;
}

export interface SystemSnapshot {
  cpuUsage: number;
  memoryUsage: number;
  memoryTotal: number;
  uptime: number;
  hostname: string;
  os: string;
  cpuName: string;
}

export interface FridayReply {
  text: string;
  actionId?: string;
  argument?: string;
  source: 'greeting' | 'command' | 'conversation' | 'fallback';
}

// ============================================================================
// Intelligence Engine, ElevenLabs & Developer Forge
// ============================================================================

export type EngineProvider = 'opencode' | 'nvidia' | 'openrouter' | 'groq';
export type EngineSource = EngineProvider | 'local' | 'demo';
export type EngineConnectionState = 'idle' | 'connecting' | 'online' | 'fallback' | 'error';

export interface EngineStatus {
  state: EngineConnectionState;
  source: EngineSource;
  model: string;
  detail?: string;
  latencyMs?: number;
  checkedAt?: Date;
}

export interface EngineModel {
  /** Stable UI id, for example `opencode/nemotron-3.5-lightning-free`. */
  id: string;
  /** Model id sent to the provider API. */
  apiModel: string;
  provider: EngineProvider;
  name: string;
  family: string;
  description: string;
  contextWindow: number;
  speed: 'fast' | 'balanced' | 'deep';
  free: boolean;
  recommended?: boolean;
  vision?: boolean;
}

export interface EngineCredentialStatus {
  opencode: boolean;
  nvidia: boolean;
  openrouter: boolean;
  elevenlabs: boolean;
  source: 'opencode-auth' | 'environment' | 'settings' | 'none';
}

export interface AiChatUsage {
  input?: number;
  output?: number;
  total?: number;
}

export interface AiChatResult {
  text: string;
  provider: EngineProvider;
  model: string;
  latencyMs: number;
  usage?: AiChatUsage;
}

export interface ElevenLabsVoice {
  id: string;
  name: string;
  description?: string;
  labels?: Record<string, string>;
  previewUrl?: string;
}

export interface DeveloperFile {
  path: string;
  content: string;
}

export interface DeveloperProject {
  id: string;
  name: string;
  title: string;
  description: string;
  path: string;
  prompt: string;
  engine: EngineSource;
  model?: string;
  files: Array<{ path: string; bytes: number }>;
  createdAt: Date;
}

export type DeveloperTaskStatus =
  | 'idle'
  | 'planning'
  | 'generating'
  | 'writing'
  | 'ready'
  | 'error';

export type DeveloperStepStatus = 'pending' | 'running' | 'complete' | 'failed';

export interface DeveloperTaskStep {
  id: string;
  label: string;
  status: DeveloperStepStatus;
  detail?: string;
  startedAt?: Date;
  completedAt?: Date;
}

export interface DeveloperTask {
  id: string;
  prompt: string;
  status: DeveloperTaskStatus;
  steps: DeveloperTaskStep[];
  projectId?: string;
  error?: string;
  engine?: EngineSource;
  startedAt: Date;
  completedAt?: Date;
}