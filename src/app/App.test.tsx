import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';
import App from './App';
import {
  DEFAULT_FRIDAY_SETTINGS,
  useAssistantStore,
  useConversationsStore,
  useUIStore,
} from '@/stores';

beforeEach(() => {
  window.localStorage.clear();

  useConversationsStore.setState({
    conversations: [],
    activeConversationId: null,
    isLoading: false,
    error: null,
  });

  useUIStore.setState({
    overlay: null,
    toasts: [],
    isCommandPaletteOpen: false,
  });

  useAssistantStore.setState({
    settings: { ...DEFAULT_FRIDAY_SETTINGS },
    mood: 'idle',
    statusText: 'Online',
    isListening: false,
    isSpeaking: false,
    audioLevel: 0,
    transcript: '',
    pendingAutomation: null,
    automationLog: [],
    lastReply: null,
  });
});

describe('App', () => {
  it('renders the core and responds to a directive through the dock', async () => {
    render(<App />);

    expect(screen.getAllByText('FRIDAY').length).toBeGreaterThan(0);
    expect(
      screen.getByText(/Good (morning|afternoon|evening), sir\./)
    ).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Directive input'), {
      target: { value: 'Hello FRIDAY' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Send directive' }));

    expect(await screen.findByText(/All systems are standing by/)).toBeInTheDocument();
    expect(screen.getByText(/last directive \/ Hello FRIDAY/i)).toBeInTheDocument();
  });

  it('opens the command deck and filters automation commands', () => {
    render(<App />);

    fireEvent.keyDown(window, { key: 'k', ctrlKey: true });

    expect(
      screen.getByRole('dialog', { name: 'FRIDAY command deck' })
    ).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Search commands'), {
      target: { value: 'notepad' },
    });

    expect(screen.getByRole('option', { name: /Open Notepad/ })).toBeInTheDocument();
  });

  it('opens the settings overlay from the core header', () => {
    render(<App />);

    fireEvent.click(screen.getByRole('button', { name: 'Settings' }));

    expect(screen.getByRole('dialog', { name: 'Core settings' })).toBeInTheDocument();
    expect(screen.getByText('Persona')).toBeInTheDocument();
    expect(screen.getByText('Voice output')).toBeInTheDocument();
    expect(screen.getByText('Automation and safety')).toBeInTheDocument();
  });

  it('opens the transmission log overlay', () => {
    render(<App />);

    fireEvent.click(screen.getByRole('button', { name: 'Log' }));

    expect(screen.getByRole('dialog', { name: 'Transmission log' })).toBeInTheDocument();
    expect(screen.getByText('channel empty')).toBeInTheDocument();
  });
});
