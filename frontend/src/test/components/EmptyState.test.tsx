import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { EmptyState } from '../../components/ui/EmptyState';

describe('EmptyState', () => {
  it('renders title and description', () => {
    render(<EmptyState title="Nothing here" description="Try adding something" />);
    expect(screen.getByText('Nothing here')).toBeTruthy();
    expect(screen.getByText('Try adding something')).toBeTruthy();
  });

  it('renders an action node when provided', () => {
    render(<EmptyState title="Empty" action={<button>Create</button>} />);
    expect(screen.getByRole('button', { name: 'Create' })).toBeTruthy();
  });

  it('omits description when not provided', () => {
    const { container } = render(<EmptyState title="Only title" />);
    expect(container.querySelector('p')).toBeNull();
  });
});
