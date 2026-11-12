import { useEffect, type ReactNode } from 'react';
import { X } from 'lucide-react';
import { cn } from '@/lib/utils';

export interface OverlayProps {
  eyebrow: string;
  title: string;
  description?: string;
  accessory?: ReactNode;
  onClose: () => void;
  children: ReactNode;
  width?: 'default' | 'wide';
  height?: 'auto' | 'tall';
}

export const Overlay = ({
  eyebrow,
  title,
  description,
  accessory,
  onClose,
  children,
  width = 'default',
  height = 'auto',
}: OverlayProps) => {
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-[80] flex items-center justify-center bg-[#02040a]/80 p-3 backdrop-blur-xl sm:p-6 animate-fade-in"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <section
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className={cn(
          'overlay-shell relative flex max-h-full min-h-0 w-full flex-col overflow-hidden rounded-2xl border border-white/[0.08] bg-[#050810]/95 shadow-[0_40px_140px_rgba(0,0,0,0.8)] animate-overlay-in',
          width === 'wide' ? 'max-w-6xl' : 'max-w-5xl',
          height === 'tall' && 'h-[min(82vh,52rem)]'
        )}
      >
        <span className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-cyan-300/50 to-transparent" />
        <span className="pointer-events-none absolute -right-24 -top-24 h-64 w-64 rounded-full bg-cyan-400/[0.05] blur-3xl" />

        <header className="relative flex flex-shrink-0 items-center justify-between gap-4 border-b border-white/[0.06] px-4 py-3.5 sm:px-6">
          <div className="flex min-w-0 items-center gap-3">
            <span className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded border border-cyan-300/20 bg-cyan-300/[0.05] font-mono text-[0.6rem] font-semibold tracking-[0.08em] text-cyan-200">
              FR
            </span>
            <div className="min-w-0">
              <p className="font-mono text-[0.55rem] uppercase tracking-[0.24em] text-graphite-600">
                {eyebrow}
              </p>
              <h2 className="truncate text-sm font-medium tracking-wide text-graphite-100">{title}</h2>
            </div>
            {description && (
              <p className="ml-3 hidden max-w-md truncate border-l border-white/[0.06] pl-3 text-xs text-graphite-500 xl:block">
                {description}
              </p>
            )}
          </div>

          <div className="flex flex-shrink-0 items-center gap-2">
            {accessory}
            <button
              type="button"
              onClick={onClose}
              aria-label={`Close ${title}`}
              className="flex h-8 w-8 items-center justify-center rounded border border-white/[0.06] text-graphite-500 transition-colors hover:border-cyan-300/25 hover:text-cyan-200"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </header>

        <div className="relative min-h-0 flex-1 overflow-hidden">{children}</div>

        <footer className="flex flex-shrink-0 items-center justify-between border-t border-white/[0.06] px-4 py-2 font-mono text-[0.55rem] uppercase tracking-[0.18em] text-graphite-700 sm:px-6">
          <span className="flex items-center gap-2">
            <span className="h-1 w-1 rounded-full bg-emerald-400" />
            secure local session
          </span>
          <span>esc to return to core</span>
        </footer>
      </section>
    </div>
  );
};

Overlay.displayName = 'Overlay';

export default Overlay;
