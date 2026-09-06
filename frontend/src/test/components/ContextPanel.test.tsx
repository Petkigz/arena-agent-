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
import { useScreenshotStore } from '../../stores/screenshotStore';
import { useModelSettingsStore } from '../../stores/modelSettingsStore';

function makeMemory(id: string, title: string, importance = 5): Memory {
  return { id, title, content: '', timestamp: '', metadata: { importance, tags: [] } } as unknown as Memory;
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

describe('ContextPanel — the cognitive dashboard', () => {
  beforeEach(() => {
    usePresenceStore.setState({
      presence: {
        status: 'working',
        message: 'Planning the UI.',
        currentGoal: 'Ship Arena',
        currentTask: 'Polish UI',
        progress: 0.4,
      },
      quickActions: [],
    });
    useMemoryBrowserStore.setState({
      memories: [
        makeMemory('m1', 'Owner prefers dark mode', 8),
        makeMemory('m2', 'Kaba is the owner', 3),
        makeMemory('m3', 'Low importance note', 1),
      ],
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
          { id: 'b', role: 'user', content: 'please continue', timestamp: '' },
        ],
      },
    } as never);
    useLayoutStore.setState({ contextPanelCollapsed: false } as never);
    useScreenshotStore.setState({
      screenshots: [],
      currentScreenshot: null,
      isCapturing: false,
      isStreaming: false,
    } as never);
    useModelSettingsStore.setState({
      llmModels: [{ id: 'llm-1', name: 'Qwen Coder', description: '', size: '', performance: {} as never, enabled: true }],
      selectedLLM: 'llm-1',
    } as never);
  });

  it('renders the cognitive-dashboard sections (the reference IA)', () => {
    render(<ContextPanel />);
    for (const section of [
      'Current Goal',
      'State',
      'Focus',
      'Relevant Memory',
      'Perception',
      'Active Tools',
      'Current Chat',
      'Recent Activity',
      'Beanie insight',
    ]) {
      expect(screen.getByRole('region', { name: section }) || screen.getByLabelText(section)).toBeTruthy();
    }
  });

  it('flows every section from real store data', () => {
    render(<ContextPanel />);
    // Goal + progress
    expect(screen.getByText('Ship Arena')).toBeTruthy();
    expect(screen.getByRole('progressbar', { name: 'Goal progress' })).toBeTruthy();
    // State
    expect(screen.getByText('Working')).toBeTruthy();
    // Focus (also appears as the State activity line)
    expect(screen.getAllByText('Polish UI').length).toBeGreaterThanOrEqual(2);
    // Relevant memory: importance-ranked — the high-importance one first
    const memories = screen.getAllByText(/prefers dark mode|Kaba is the owner|Low importance note/);
    expect(memories[0].textContent).toContain('prefers dark mode');
    expect(screen.getByText('3 memories')).toBeTruthy();
    // Perception (environment shows the active LLM)
    expect(screen.getByText(/Qwen Coder/)).toBeTruthy();
    // Active tools
    expect(screen.getByText('Reading config')).toBeTruthy();
    // Current chat
    expect(screen.getByText('Test')).toBeTruthy();
    expect(screen.getByText('2 messages')).toBeTruthy();
    // Beanie insight — the light at the bottom
    expect(screen.getByText('Planning the UI.')).toBeTruthy();
  });

  it('shows in-progress tools as active, not the completed tail', () => {
    render(<ContextPanel />);
    expect(screen.getByText('Reading config')).toBeTruthy(); // in_progress
    expect(screen.queryByText('Searching files')).toBeNull(); // complete — history, not active
  });

  it('renders perception state honestly (screen idle, vision inactive until data exists)', () => {
    render(<ContextPanel />);
    expect(screen.getByText('Idle')).toBeTruthy();
    expect(screen.getByText('Not active')).toBeTruthy();
  });

  it('still does NOT render dashboard statistics (a mind, not a metrics sidebar)', () => {
    render(<ContextPanel />);
    expect(screen.queryByText('Statistics')).toBeNull();
    expect(screen.queryByText('Knowledge Graph')).toBeNull();
  });

  it('shows quiet placeholders when the mind is empty', () => {
    usePresenceStore.setState({ presence: { status: 'idle', message: "I'm here." } });
    useProjectStore.setState({ projects: [] } as never);
    useMemoryBrowserStore.setState({ memories: [] } as never);
    useConversationStore.setState({ currentConversation: null } as never);
    render(<ContextPanel />);
    expect(screen.getByText('No active goal')).toBeTruthy();
    expect(screen.getByText('No memories yet')).toBeTruthy();
    expect(screen.getByText('Quiet', { exact: false })).toBeTruthy();
    expect(screen.getByText('No conversation')).toBeTruthy();
    expect(screen.getByText('Nothing yet')).toBeTruthy();
  });
});
