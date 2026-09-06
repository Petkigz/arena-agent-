import { render, screen } from '@testing-library/react';
import { describe, it, expect, beforeEach } from 'vitest';
import { ContextPanel } from '../../components/layout/ContextPanel';
import { usePresenceStore } from '../../stores/presenceStore';
import { useMemoryBrowserStore } from '../../stores/memoryBrowserStore';
import type { Memory } from '../../stores/memoryBrowserStore';
import { useProjectStore } from '../../stores/projectStore';
import type { Project } from '../../stores/projectStore';
import { useConversationStore } from '../../stores/conversationStore';
import { useLayoutStore } from '../../stores/layoutStore';

function makeMemory(id: string, title: string): Memory {
  return { id, title, content: '', timestamp: '', metadata: { importance: 5, tags: [] } } as unknown as Memory;
}

function makeProject(name: string, status: Project['status']): Project {
  return {
    id: 'p1',
    name,
    description: '',
    status,
    tasks: [],
    files: [],
    conversations: [],
    createdAt: '',
    updatedAt: '',
  } as unknown as Project;
}

describe('ContextPanel — the agent\'s mind', () => {
  beforeEach(() => {
    usePresenceStore.setState({
      presence: { status: 'idle', message: "I'm here.", currentGoal: 'Ship Arena', currentTask: 'Polish UI' },
      quickActions: [],
    });
    useMemoryBrowserStore.setState({
      memories: [makeMemory('m1', 'Owner prefers dark mode'), makeMemory('m2', 'Kaba is the owner')],
    } as never);
    useProjectStore.setState({ projects: [makeProject('Arena revival', 'active')] } as never);
    useConversationStore.setState({
      currentConversation: {
        id: 'c1',
        title: 'Test',
        messages: [
          { id: 'a', role: 'assistant', content: 'done', timestamp: '', status: 'complete', actionSteps: [
            { id: 's1', description: 'Searching files', status: 'complete' },
            { id: 's2', description: 'Reading config', status: 'in_progress' },
          ] },
        ],
      },
    } as never);
    useLayoutStore.setState({ contextPanelCollapsed: false } as never);
  });

  it('renders the agent-mind sections: Mission, Working on, Memory, Tools', () => {
    render(<ContextPanel />);
    expect(screen.getByText('Mission')).toBeTruthy();
    expect(screen.getByText('Working on')).toBeTruthy();
    expect(screen.getByText('Memory')).toBeTruthy();
    expect(screen.getByText('Tools')).toBeTruthy();
    // Content flows from the stores.
    expect(screen.getByText('Ship Arena')).toBeTruthy();
    expect(screen.getByText('Arena revival')).toBeTruthy();
    expect(screen.getByText('• Owner prefers dark mode')).toBeTruthy();
  });

  it('renders tool activity semantically (execution timeline, not raw output)', () => {
    render(<ContextPanel />);
    expect(screen.getByText('Searching files')).toBeTruthy();
    expect(screen.getByText('Reading config')).toBeTruthy();
  });

  it('does NOT render dashboard statistics (the panel is a mind, not a metrics sidebar)', () => {
    render(<ContextPanel />);
    expect(screen.queryByText('Statistics')).toBeNull();
    expect(screen.queryByText('Knowledge Graph')).toBeNull();
    expect(screen.queryByText('Current Chat')).toBeNull();
  });

  it('shows quiet placeholders when the mind is empty', () => {
    usePresenceStore.setState({ presence: { status: 'idle', message: "I'm here." } });
    useProjectStore.setState({ projects: [] } as never);
    useMemoryBrowserStore.setState({ memories: [] } as never);
    useConversationStore.setState({ currentConversation: null } as never);
    render(<ContextPanel />);
    expect(screen.getByText('No active mission')).toBeTruthy();
    expect(screen.getByText('No memories yet')).toBeTruthy();
    expect(screen.getByText('Quiet', { exact: false })).toBeTruthy();
  });
});
