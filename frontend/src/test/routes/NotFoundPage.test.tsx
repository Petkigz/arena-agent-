import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, it, expect } from 'vitest';
import { NotFoundPage } from '../../app/routes/NotFoundPage';

function renderNotFound() {
  return render(
    <MemoryRouter>
      <NotFoundPage />
    </MemoryRouter>
  );
}

describe('NotFoundPage', () => {
  it('renders the 404 heading and message', () => {
    renderNotFound();
    expect(screen.getByText('404')).toBeTruthy();
    expect(screen.getByText('Page Not Found')).toBeTruthy();
  });

  it('renders Go Back and Home buttons', () => {
    renderNotFound();
    expect(screen.getByRole('button', { name: 'Go Back' })).toBeTruthy();
    expect(screen.getByRole('button', { name: /Home/ })).toBeTruthy();
  });
});
