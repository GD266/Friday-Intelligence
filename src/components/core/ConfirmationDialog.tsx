import { useEffect, useState } from 'react';
import { AlertTriangle, ShieldAlert, X } from 'lucide-react';
import { useAssistantStore } from '@/stores';
import { confirmPendingAutomation, cancelPendingAutomation } from '@/lib/automation-runner';
import { Button } from '@/components/ui/Button';
import type { AutomationAction, AutomationResult } from '@/types';

export interface ConfirmationDialogProps {
  onExecuted?: (target: AutomationAction, result: AutomationResult) => void;
  onCancelled?: (target: AutomationAction) => void;
}

export const ConfirmationDialog = ({ onExecuted, onCancelled }: ConfirmationDialogProps) => {
  const pending = useAssistantStore((state) => state.pendingAutomation);
  const [isRunning, setIsRunning] = useState(false);

  useEffect(() => {
    if (!pending) {
      setIsRunning(false);
      return;
    }

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        cancelPendingAutomation();
        onCancelled?.(pending.action);
      }
    };

    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [pending, onCancelled]);

  if (!pending) return null;

  const { action, argument, requestedBy } = pending;
  const isHighRisk = action.risk === 'high';

  const handleCancel = () => {
    cancelPendingAutomation();
    onCancelled?.(action);
  };

  const handleConfirm = async () => {
    if (isRunning) return;
    setIsRunning(true);

    const target = action;
    const result = await confirmPendingAutomation();
    setIsRunning(false);

    if (result) {
      onExecuted?.(target, result);
    } else {
      onCancelled?.(target);
    }
  };

  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm animate-fade-in">
      <div
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="friday-confirm-title"
        aria-describedby="friday-confirm-description"
        className="w-full max-w-lg overflow-hidden rounded-xl border border-border-primary bg-graphite-950/95 shadow-overlay"
      >
        <div className="h-px w-full bg-gradient-to-r from-transparent via-accent-blue/70 to-transparent" />

        <div className="flex items-start gap-4 p-6">
          <div
            className={`flex h-11 w-11 flex-shrink-0 items-center justify-center rounded-lg border ${
              isHighRisk
                ? 'border-red-500/30 bg-red-500/10 text-red-300'
                : 'border-amber-500/30 bg-amber-500/10 text-amber-300'
            }`}
          >
            {isHighRisk ? (
              <ShieldAlert className="h-5 w-5" />
            ) : (
              <AlertTriangle className="h-5 w-5" />
            )}
          </div>

          <div className="min-w-0 flex-1">
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="text-[0.65rem] font-semibold uppercase tracking-[0.22em] text-graphite-500">
                  Confirmation required
                </p>
                <h2 id="friday-confirm-title" className="mt-1 text-lg font-semibold text-graphite-50">
                  {action.label}
                </h2>
              </div>
              <button
                type="button"
                className="rounded-md p-1 text-graphite-500 transition-colors hover:bg-graphite-800 hover:text-graphite-100"
                onClick={handleCancel}
                aria-label="Cancel action"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <p id="friday-confirm-description" className="mt-2 text-sm leading-relaxed text-graphite-300">
              {action.description}
            </p>

            {argument && (
              <div className="mt-3 rounded-md border border-border-subtle bg-graphite-900/70 px-3 py-2">
                <p className="text-[0.65rem] uppercase tracking-wider text-graphite-500">
                  {action.argumentLabel ?? 'Argument'}
                </p>
                <p className="mt-1 break-all font-mono text-xs text-graphite-200">{argument}</p>
              </div>
            )}

            <div className="mt-3 flex flex-wrap items-center gap-2 text-[0.7rem]">
              <span
                className={`rounded-full border px-2 py-0.5 font-medium uppercase tracking-wider ${
                  isHighRisk
                    ? 'border-red-500/30 bg-red-500/10 text-red-300'
                    : 'border-amber-500/30 bg-amber-500/10 text-amber-300'
                }`}
              >
                {action.risk} risk
              </span>
              <span className="rounded-full border border-border-primary bg-graphite-900 px-2 py-0.5 text-graphite-400">
                Requested by {requestedBy.replace('-', ' ')}
              </span>
            </div>

            {isHighRisk && (
              <p className="mt-3 text-xs leading-relaxed text-red-300/90">
                This operation can affect your files, privacy, or current session. FRIDAY will
                never run it without your approval.
              </p>
            )}
          </div>
        </div>

        <div className="flex items-center justify-end gap-2 border-t border-border-subtle bg-graphite-900/40 px-6 py-4">
          <Button variant="ghost" onClick={handleCancel} disabled={isRunning}>
            Cancel
          </Button>
          <Button
            variant={isHighRisk ? 'danger' : 'primary'}
            onClick={() => void handleConfirm()}
            isLoading={isRunning}
            autoFocus
          >
            {isRunning ? 'Executing…' : isHighRisk ? 'Approve and execute' : 'Proceed'}
          </Button>
        </div>
      </div>
    </div>
  );
};

ConfirmationDialog.displayName = 'ConfirmationDialog';

export default ConfirmationDialog;
