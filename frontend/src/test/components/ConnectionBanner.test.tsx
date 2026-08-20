import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, beforeEach } from 'vitest';
import { ConnectionBanner } from '../../components/ui/ConnectionBanner';
import { webSocketService } from '../../services/websocket';

describe('ConnectionBanner', () => {
  beforeEach(() => {
    // The service starts 'disconnected' in a fresh test environment.
    webSocketService.disconnect();
  });

  it('shows the disconnected banner with a reconnect action', () => {
    render(<ConnectionBanner />);
    expect(screen.getByText('Disconnected from Arena backend')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Reconnect to server' })).toBeTruthy();
  });

  it('dismisses the banner when the dismiss button is clicked', () => {
    render(<ConnectionBanner />);
    fireEvent.click(screen.getByRole('button', { name: 'Dismiss notification' }));
    expect(screen.queryByText('Disconnected from Arena backend')).toBeNull();
  });
});
