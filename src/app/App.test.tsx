import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';
import App from './App';

beforeEach(() => {
  window.localStorage.clear();
});

describe('App', () => {
  it('renders the workspace and creates a local conversation message', () => {
    render(<App />);

    expect(screen.getAllByText('FRIDAY Intelligence').length).toBeGreaterThan(0);
    expect(screen.getByText('Start a conversation by sending a message')).toBeInTheDocument();

    fireEvent.change(screen.getByPlaceholderText('Type a message…'), {
      target: { value: 'Hello FRIDAY' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Send' }));

    expect(screen.getByText('Hello FRIDAY')).toBeInTheDocument();
  });
});
