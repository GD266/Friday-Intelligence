import { useCallback, useEffect, useRef } from 'react';
import { CoreStage } from '@/components/core/CoreStage';
import { CommandPalette } from '@/components/core/CommandPalette';
import { ConfirmationDialog } from '@/components/core/ConfirmationDialog';
import { Overlay } from '@/components/core/Overlay';
import { TransmissionLog } from '@/components/core/TransmissionLog';
import { ToastViewport } from '@/components/core/ToastViewport';
import { SettingsView } from '@/components/settings/SettingsView';
import { AutomationView } from '@/components/automation/AutomationView';
import { useAssistantStore, useConversationsStore, useSystemStore, useUIStore } from '@/stores';
import { useTelemetry } from '@/hooks/useTelemetry';
import { useFridayVoice } from '@/hooks/useFridayVoice';
import {
  automationResultReply,
  cancellationReply,
  respondToFriday,
} from '@/lib/friday';
import { findAutomationAction, requiresAutomationConfirmation } from '@/lib/automation';
import { runAutomationNow } from '@/lib/automation-runner';
import type { AutomationAction, AutomationResult, SystemSnapshot } from '@/types';

const messageMetadata = {
  modelId: 'friday-core-demo',
  providerId: 'custom' as const,
};

export default function App() {
  const conversations = useConversationsStore((state) => state.conversations);
  const activeConversationId = useConversationsStore((state) => state.activeConversationId);
  const createConversation = useConversationsStore((state) => state.createConversation);
  const renameConversation = useConversationsStore((state) => state.renameConversation);
  const addMessage = useConversationsStore((state) => state.addMessage);
  const mood = useAssistantStore((state) => state.mood);
  const overlay = useUIStore((state) => state.overlay);
  const closeOverlay = useUIStore((state) => state.closeOverlay);

  const handleInputRef = useRef<(text: string) => void>(() => undefined);

  const voice = useFridayVoice({
    onTranscript: (text) => handleInputRef.current(text),
  });
  const {
    speak,
    toggleListening,
    cancelListening,
    isListening,
    isSpeaking,
    audioLevel,
    transcript,
    voiceError,
    clearVoiceError,
    dictationSupported,
  } = voice;

  useTelemetry();

  const activeConversation =
    conversations.find((conversation) => conversation.id === activeConversationId) ?? null;

  const appendAssistantMessage = useCallback(
    async (text: string) => {
      let conversationId = useConversationsStore.getState().activeConversationId;
      if (!conversationId) {
        const conversation = createConversation({ title: 'FRIDAY session' });
        conversationId = conversation.id;
      }

      addMessage(conversationId, text, 'assistant', messageMetadata);
      useAssistantStore.getState().setLastReply(text);

      const settings = useAssistantStore.getState().settings;
      if (settings.autoSpeak && settings.voiceEnabled) {
        await speak(text);
      } else {
        const assistant = useAssistantStore.getState();
        assistant.setMood('idle');
        assistant.setStatusText('Online');
      }
    },
    [addMessage, createConversation, speak]
  );

  const handleUserInput = useCallback(
    async (content: string, source: 'text' | 'voice' = 'text') => {
      const trimmed = content.trim();
      if (!trimmed) return;

      const assistant = useAssistantStore.getState();
      if (assistant.mood === 'thinking') return;

      assistant.setMood('thinking');
      assistant.setStatusText('Processing');

      const conversationTitle = trimmed.length > 60 ? `${trimmed.slice(0, 60)}…` : trimmed;
      const conversationsStore = useConversationsStore.getState();
      let conversationId = conversationsStore.activeConversationId;
      let shouldRename = false;

      if (!conversationId) {
        const conversation = createConversation({ title: conversationTitle });
        conversationId = conversation.id;
      } else {
        const existing = conversationsStore.conversations.find(
          (conversation) => conversation.id === conversationId
        );
        shouldRename =
          !existing ||
          existing.messages.length === 0 ||
          existing.title === 'New conversation' ||
          existing.title === 'FRIDAY session';
      }

      addMessage(conversationId, trimmed, 'user', messageMetadata);

      // A conversation created by an assistant reply or a new session still has a
      // placeholder title. The first user message gives it a meaningful name.
      if (shouldRename) renameConversation(conversationId, conversationTitle);

      try {
        // A short deliberate beat sells the processing state without blocking the UI.
        await new Promise((resolve) => window.setTimeout(resolve, 260));

        const settings = useAssistantStore.getState().settings;
        const status = useSystemStore.getState().status;
        const snapshot: SystemSnapshot | null =
          status.hostname || status.cpuName
            ? {
                cpuUsage: status.cpuUsage,
                memoryUsage: status.memoryUsage,
                memoryTotal: status.memoryTotal,
                uptime: status.uptime,
                hostname: status.hostname ?? 'this workstation',
                os: status.os ?? 'Windows',
                cpuName: status.cpuName ?? '',
              }
            : null;

        const reply = respondToFriday(trimmed, settings, snapshot);
        const requestedBy = source === 'voice' ? 'voice' : 'text';

        if (reply.actionId) {
          const target = findAutomationAction(reply.actionId);

          if (target) {
            if (requiresAutomationConfirmation(target, settings)) {
              useAssistantStore.getState().requestAutomation({
                action: target,
                argument: reply.argument,
                requestedBy,
              });
              await appendAssistantMessage(reply.text);
              return;
            }

            const result = await runAutomationNow(target, reply.argument);
            await appendAssistantMessage(automationResultReply(target, result, settings));
            return;
          }
        }

        await appendAssistantMessage(reply.text);
      } catch (error) {
        const message =
          error instanceof Error ? error.message : 'An unexpected local core error occurred.';
        const conversationStillExists = useConversationsStore
          .getState()
          .conversations.some((conversation) => conversation.id === conversationId);

        if (conversationStillExists) {
          addMessage(conversationId, message, 'system');
        }

        const current = useAssistantStore.getState();
        current.setMood('idle');
        current.setStatusText('Online');
        current.setLastReply(message);
      }
    },
    [addMessage, appendAssistantMessage, createConversation, renameConversation]
  );

  useEffect(() => {
    handleInputRef.current = (text) => {
      void handleUserInput(text, 'voice');
    };
  }, [handleUserInput]);

  // Overlays temporarily pause the microphone so a settings or audit view never
  // captures a directive out of context.
  useEffect(() => {
    if (overlay && isListening) {
      void cancelListening();
    }
  }, [cancelListening, isListening, overlay]);

  const handleAutomationExecuted = useCallback(
    async (target: AutomationAction, result: AutomationResult) => {
      const settings = useAssistantStore.getState().settings;
      await appendAssistantMessage(automationResultReply(target, result, settings));
    },
    [appendAssistantMessage]
  );

  const handleAutomationCancelled = useCallback(async () => {
    const settings = useAssistantStore.getState().settings;
    await appendAssistantMessage(cancellationReply(settings));
  }, [appendAssistantMessage]);

  return (
    <>
      <CoreStage
        messages={activeConversation?.messages ?? []}
        onSend={(text) => void handleUserInput(text, 'text')}
        isBusy={mood === 'thinking'}
        isListening={isListening}
        isSpeaking={isSpeaking}
        audioLevel={audioLevel}
        transcript={transcript}
        voiceError={voiceError}
        onToggleListening={() => void toggleListening()}
        onDismissVoiceError={clearVoiceError}
        dictationSupported={dictationSupported}
      />

      <CommandPalette />

      <ConfirmationDialog
        onExecuted={(target, result) => void handleAutomationExecuted(target, result)}
        onCancelled={() => void handleAutomationCancelled()}
      />

      {overlay === 'log' && <TransmissionLog onClose={closeOverlay} />}

      {overlay === 'settings' && (
        <Overlay
          eyebrow="Configuration / core profile"
          title="Core settings"
          description="Persona, female voice profile, safety, and native telemetry."
          onClose={closeOverlay}
        >
          <SettingsView />
        </Overlay>
      )}

      {overlay === 'automation' && (
        <Overlay
          eyebrow="Desktop control / audited actions"
          title="Automation console"
          description="Allowlisted Windows actions with mandatory approval for high-risk operations."
          onClose={closeOverlay}
          width="wide"
        >
          <AutomationView />
        </Overlay>
      )}

      <ToastViewport />
    </>
  );
}
