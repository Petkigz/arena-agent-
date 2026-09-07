import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it } from 'vitest';
import { Modal } from '../../components/ui/Modal';

afterEach(() => { cleanup(); document.querySelector('#audit-opener')?.remove(); });

it('uses one container-scoped focus trap and restores the opener', () => {
  const opener = document.createElement('button');
  opener.id = 'audit-opener';
  opener.textContent = 'Outside the dialog';
  document.body.append(opener);
  opener.focus();

  const { rerender } = render(<Modal isOpen onClose={() => {}} title="Review">
    <button>First field</button><button disabled>Unavailable</button><button>Last field</button>
  </Modal>);
  const dialog = screen.getByRole('dialog');
  const first = screen.getByRole('button', { name: 'Close modal' });
  const last = screen.getByRole('button', { name: 'Last field' });
  expect(document.activeElement).toBe(first);
  last.focus();
  fireEvent.keyDown(dialog, { key: 'Tab' });
  expect(document.activeElement).toBe(first);
  fireEvent.keyDown(dialog, { key: 'Tab', shiftKey: true });
  expect(document.activeElement).toBe(last);
  expect(document.activeElement).not.toBe(opener);

  rerender(<Modal isOpen={false} onClose={() => {}} title="Review"><button>First field</button></Modal>);
  expect(document.activeElement).toBe(opener);
});
