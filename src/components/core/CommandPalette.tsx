import { useEffect, useMemo, useRef, useState } from 'react';
import {
  ArrowDown,
  ArrowUp,
  CornerDownLeft,
  History,
  MessageSquarePlus,
  Search as SearchIcon,
  Settings2,
  ShieldCheck,
  Sparkles,
  Workflow,
  type LucideIcon,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { useConversationsStore, useUIStore } from '@/stores';
import { AUTOMATION_ACTIONS } from '@/lib/automation';
import { requestAutomation } from '@/lib/automation-runner';

interface PaletteItem {
  id: string;
  label: string;
  description: string;
  group: string;
  keywords: string[];
  icon: LucideIcon;
  run: () => void | Promise<void>;
}

export const CommandPalette = () => {
  const isOpen = useUIStore((state) => state.isCommandPaletteOpen);
  const setCommandPaletteOpen = useUIStore((state) => state.setCommandPaletteOpen);
  const toggleCommandPalette = useUIStore((state) => state.toggleCommandPalette);
  const openOverlay = useUIStore((state) => state.openOverlay);
  const createConversation = useConversationsStore((state) => state.createConversation);

  const [query, setQuery] = useState('');
  const [selectedIndex, setSelectedIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  const items = useMemo<PaletteItem[]>(() => {
    const automationItems = AUTOMATION_ACTIONS.filter((action) => !action.argumentLabel).map(
      (action) => ({
        id: `automation-${action.id}`,
        label: action.label,
        description: action.description,
        group: 'Automation',
        keywords: [action.id, ...action.keywords, action.category, action.risk],
        icon: ShieldCheck,
        run: async () => {
          await requestAutomation(action, undefined, 'command-palette');
        },
      })
    );

    return [
      {
        id: 'new-session',
        label: 'New session',
        description: 'Clear the core and begin a fresh local session.',
        group: 'Core',
        keywords: ['new', 'session', 'conversation', 'reset', 'start'],
        icon: MessageSquarePlus,
        run: () => {
          createConversation();
        },
      },
      {
        id: 'open-log',
        label: 'Open transmission log',
        description: 'Review every directive and response in this workspace.',
        group: 'Core',
        keywords: ['log', 'history', 'transcript', 'messages', 'archive'],
        icon: History,
        run: () => openOverlay('log'),
      },
      {
        id: 'open-settings',
        label: 'Open core settings',
        description: 'Persona, voice profile, safety policy, and telemetry.',
        group: 'Core',
        keywords: ['settings', 'voice', 'persona', 'female', 'safety', 'configuration'],
        icon: Settings2,
        run: () => openOverlay('settings'),
      },
      {
        id: 'open-automation',
        label: 'Open automation console',
        description: 'Browse the audited desktop action catalog and audit log.',
        group: 'Core',
        keywords: ['automation', 'actions', 'desktop', 'control', 'audit'],
        icon: Workflow,
        run: () => openOverlay('automation'),
      },
      ...automationItems,
    ];
  }, [createConversation, openOverlay]);

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return items;

    return items.filter((item) =>
      [item.label, item.description, ...item.keywords]
        .join(' ')
        .toLowerCase()
        .includes(needle)
    );
  }, [items, query]);

  useEffect(() => {
    if (!isOpen) return;

    setQuery('');
    setSelectedIndex(0);
    const frame = window.requestAnimationFrame(() => inputRef.current?.focus());
    return () => window.cancelAnimationFrame(frame);
  }, [isOpen]);

  useEffect(() => {
    setSelectedIndex(0);
  }, [query]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        toggleCommandPalette();
      }
    };

    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [toggleCommandPalette]);

  useEffect(() => {
    if (!isOpen) return;

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        setCommandPaletteOpen(false);
        return;
      }

      if (event.key === 'ArrowDown') {
        event.preventDefault();
        setSelectedIndex((index) => (filtered.length ? (index + 1) % filtered.length : 0));
        return;
      }

      if (event.key === 'ArrowUp') {
        event.preventDefault();
        setSelectedIndex((index) =>
          filtered.length ? (index - 1 + filtered.length) % filtered.length : 0
        );
        return;
      }

      if (event.key === 'Enter') {
        event.preventDefault();
        const selected = filtered[selectedIndex];
        if (selected) {
          setCommandPaletteOpen(false);
          void selected.run();
        }
      }
    };

    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [filtered, isOpen, selectedIndex, setCommandPaletteOpen]);

  useEffect(() => {
    const selected = filtered[selectedIndex];
    if (!selected) return;
    const element = document.getElementById(`friday-palette-${selected.id}`);
    if (element && typeof element.scrollIntoView === 'function') {
      element.scrollIntoView({ block: 'nearest' });
    }
  }, [filtered, selectedIndex]);

  if (!isOpen) return null;

  let lastGroup = '';

  return (
    <div
      className="fixed inset-0 z-[110] flex items-start justify-center bg-[#02040a]/75 px-4 pt-[13vh] backdrop-blur-xl animate-fade-in"
      onClick={() => setCommandPaletteOpen(false)}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label="FRIDAY command deck"
        className="relative w-full max-w-2xl overflow-hidden rounded-xl border border-white/[0.09] bg-[#050810]/95 shadow-[0_40px_140px_rgba(0,0,0,0.85)] animate-overlay-in"
        onClick={(event) => event.stopPropagation()}
      >
        <span className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-cyan-300/60 to-transparent" />

        <div className="flex items-center gap-3 border-b border-white/[0.06] px-4 py-3">
          <span className="flex items-center gap-1.5 font-mono text-[0.6rem] uppercase tracking-[0.18em] text-cyan-300/70">
            <Sparkles className="h-3 w-3" />
            cmd
          </span>
          <SearchIcon className="h-4 w-4 flex-shrink-0 text-cyan-300/60" />
          <input
            ref={inputRef}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search commands, sessions, and automation…"
            className="w-full bg-transparent font-mono text-sm text-graphite-100 placeholder-graphite-600 focus:outline-none"
            aria-label="Search commands"
            autoComplete="off"
            spellCheck={false}
          />
          <kbd className="hidden rounded border border-white/[0.08] bg-white/[0.02] px-1.5 py-0.5 font-mono text-[0.55rem] text-graphite-500 sm:block">
            ESC
          </kbd>
        </div>

        <div className="max-h-[52vh] overflow-y-auto scrollbar-thin p-2" role="listbox" aria-label="Commands">
          {filtered.length === 0 && (
            <div className="px-4 py-10 text-center font-mono text-xs text-graphite-500">
              No commands match “{query}”.
            </div>
          )}

          {filtered.map((item, index) => {
            const showGroup = item.group !== lastGroup;
            lastGroup = item.group;
            const Icon = item.icon;
            const isSelected = index === selectedIndex;

            return (
              <div key={item.id}>
                {showGroup && (
                  <p className="px-3 pb-1 pt-3 font-mono text-[0.52rem] font-semibold uppercase tracking-[0.24em] text-graphite-600">
                    {item.group}
                  </p>
                )}
                <button
                  type="button"
                  id={`friday-palette-${item.id}`}
                  role="option"
                  aria-selected={isSelected}
                  className={cn(
                    'group flex w-full items-start gap-3 rounded-md border px-3 py-2.5 text-left transition-colors',
                    isSelected
                      ? 'border-cyan-300/[0.15] bg-cyan-300/[0.05] text-graphite-50'
                      : 'border-transparent text-graphite-300 hover:bg-white/[0.025]'
                  )}
                  onMouseEnter={() => setSelectedIndex(index)}
                  onClick={() => {
                    setCommandPaletteOpen(false);
                    void item.run();
                  }}
                >
                  <span
                    className={cn(
                      'mt-0.5 flex h-7 w-7 flex-shrink-0 items-center justify-center rounded border',
                      isSelected
                        ? 'border-cyan-300/25 bg-cyan-300/[0.07] text-cyan-200'
                        : 'border-white/[0.06] bg-white/[0.02] text-graphite-500'
                    )}
                  >
                    <Icon className="h-3.5 w-3.5" />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-medium">{item.label}</span>
                    <span className="mt-0.5 block truncate text-xs text-graphite-500">
                      {item.description}
                    </span>
                  </span>
                  {isSelected && (
                    <CornerDownLeft className="mt-1 h-3.5 w-3.5 flex-shrink-0 text-cyan-300/50" />
                  )}
                </button>
              </div>
            );
          })}
        </div>

        <div className="flex flex-wrap items-center justify-between gap-2 border-t border-white/[0.06] bg-white/[0.01] px-4 py-2 font-mono text-[0.55rem] uppercase tracking-[0.14em] text-graphite-600">
          <span className="flex items-center gap-1.5">
            <span className="h-1 w-1 rounded-full bg-emerald-400" />
            {filtered.length} command{filtered.length === 1 ? '' : 's'} indexed
          </span>
          <span className="flex items-center gap-3">
            <span className="flex items-center gap-1">
              <ArrowUp className="h-3 w-3" />
              <ArrowDown className="h-3 w-3" />
              navigate
            </span>
            <span className="flex items-center gap-1">
              <CornerDownLeft className="h-3 w-3" />
              execute
            </span>
          </span>
        </div>
      </div>
    </div>
  );
};

CommandPalette.displayName = 'CommandPalette';

export default CommandPalette;
