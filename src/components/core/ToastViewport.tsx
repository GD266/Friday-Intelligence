import { useEffect } from 'react';
import { AlertTriangle, CheckCircle2, Info, X, XCircle } from 'lucide-react';
import { useUIStore } from '@/stores';
import { cn } from '@/lib/utils';
import type { ToastState } from '@/types';

const toastStyles = {
  success: {
    icon: CheckCircle2,
    tone: 'text-emerald-300',
    border: 'border-emerald-400/20',
    glow: 'from-emerald-400/20',
  },
  error: {
    icon: XCircle,
    tone: 'text-red-300',
    border: 'border-red-400/20',
    glow: 'from-red-400/20',
  },
  warning: {
    icon: AlertTriangle,
    tone: 'text-amber-300',
    border: 'border-amber-400/20',
    glow: 'from-amber-400/20',
  },
  info: {
    icon: Info,
    tone: 'text-cyan-300',
    border: 'border-cyan-400/20',
    glow: 'from-cyan-400/20',
  },
} as const;

const ToastCard = ({ toast }: { toast: ToastState }) => {
  const removeToast = useUIStore((state) => state.removeToast);
  const style = toastStyles[toast.type];
  const Icon = style.icon;

  useEffect(() => {
    const duration = toast.duration ?? 4200;
    const timer = window.setTimeout(() => removeToast(toast.id), duration);
    return () => window.clearTimeout(timer);
  }, [removeToast, toast.duration, toast.id]);

  return (
    <div
      role="status"
      className={cn(
        'pointer-events-auto relative overflow-hidden rounded-lg border bg-[#070b12]/95 px-4 py-3 shadow-[0_20px_60px_rgba(0,0,0,0.5)] backdrop-blur-xl animate-toast-in',
        style.border
      )}
    >
      <div className={cn('absolute inset-y-0 left-0 w-px bg-gradient-to-b to-transparent', style.glow)} />
      <div className="flex items-start gap-3">
        <Icon className={cn('mt-0.5 h-4 w-4 flex-shrink-0', style.tone)} />
        <div className="min-w-0 flex-1">
          <p className="font-mono text-[0.62rem] uppercase tracking-[0.18em] text-graphite-500">
            {toast.type}
          </p>
          <p className="mt-1 text-sm font-medium text-graphite-100">{toast.title}</p>
          {toast.message && (
            <p className="mt-1 text-xs leading-relaxed text-graphite-400">{toast.message}</p>
          )}
          {toast.action && (
            <button
              type="button"
              className="mt-2 font-mono text-[0.65rem] uppercase tracking-wider text-accent-blue hover:text-cyan-200"
              onClick={() => {
                toast.action?.onClick();
                removeToast(toast.id);
              }}
            >
              {toast.action.label}
            </button>
          )}
        </div>
        <button
          type="button"
          className="rounded p-0.5 text-graphite-600 transition-colors hover:text-graphite-200"
          onClick={() => removeToast(toast.id)}
          aria-label="Dismiss notification"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
  );
};

export const ToastViewport = () => {
  const toasts = useUIStore((state) => state.toasts);

  if (toasts.length === 0) return null;

  return (
    <div className="pointer-events-none fixed bottom-6 left-4 z-[120] flex w-80 max-w-[calc(100vw-2rem)] flex-col gap-2 sm:left-8">
      {toasts.map((toast) => (
        <ToastCard key={toast.id} toast={toast} />
      ))}
    </div>
  );
};

ToastViewport.displayName = 'ToastViewport';

export default ToastViewport;
