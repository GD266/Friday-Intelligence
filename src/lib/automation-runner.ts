import { useAssistantStore, useUIStore } from '@/stores';
import { executeAutomation, requiresAutomationConfirmation } from './automation';
import { generateId } from './utils';
import type {
  AutomationAction,
  AutomationResult,
  PendingAutomation,
} from '@/types';

export type AutomationOutcome =
  | { kind: 'pending'; pending: PendingAutomation }
  | { kind: 'executed'; result: AutomationResult };

/**
 * Executes an allowlisted action immediately, recording it in the audit log and
 * surfacing a toast. Confirmation policy is intentionally handled by the caller.
 */
export async function runAutomationNow(
  target: AutomationAction,
  argument?: string
): Promise<AutomationResult> {
  const assistant = useAssistantStore.getState();

  const entry = {
    id: generateId('automation'),
    actionId: target.id,
    label: target.label,
    risk: target.risk,
    status: 'running' as const,
    message: 'Executing…',
    timestamp: new Date(),
  };

  assistant.addAutomationLog(entry);
  const startedAt = Date.now();

  const result = await executeAutomation(target.id, argument);
  const durationMs = Date.now() - startedAt;

  useAssistantStore.getState().updateAutomationLog(entry.id, {
    status: result.success ? 'success' : 'failed',
    message: result.message,
    durationMs,
  });

  useUIStore.getState().addToast(
    result.success
      ? {
          type: 'success',
          title: target.label,
          message: result.message,
          duration: 3200,
        }
      : {
          type: 'error',
          title: `${target.label} failed`,
          message: result.message,
          duration: 5200,
        }
  );

  return result;
}

/**
 * Routes an action through the confirmation policy. High-risk actions always
 * require approval; medium-risk actions follow the user's safety setting.
 */
export async function requestAutomation(
  target: AutomationAction,
  argument: string | undefined,
  requestedBy: PendingAutomation['requestedBy']
): Promise<AutomationOutcome> {
  const settings = useAssistantStore.getState().settings;

  if (requiresAutomationConfirmation(target, settings)) {
    const pending: PendingAutomation = { action: target, argument, requestedBy };
    useAssistantStore.getState().requestAutomation(pending);
    return { kind: 'pending', pending };
  }

  return { kind: 'executed', result: await runAutomationNow(target, argument) };
}

/** Approves the pending action, clears it, and executes it with an audit log. */
export async function confirmPendingAutomation(): Promise<AutomationResult | null> {
  const pending = useAssistantStore.getState().pendingAutomation;
  if (!pending) return null;

  useAssistantStore.getState().clearPendingAutomation();
  return runAutomationNow(pending.action, pending.argument);
}

/** Dismisses the pending action without executing anything. */
export function cancelPendingAutomation(): PendingAutomation | null {
  const pending = useAssistantStore.getState().pendingAutomation;
  useAssistantStore.getState().clearPendingAutomation();
  return pending;
}
