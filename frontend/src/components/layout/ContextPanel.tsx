import { useMemo } from 'react';
import type { ReactNode } from 'react';
import {
  usePresenceStore,
  useMemoryBrowserStore,
  useConversationStore,
  useLayoutStore,
  useScreenshotStore,
  useModelSettingsStore,
  useSettingsStore,
} from '../../stores';
import { Target, Activity, Crosshair, Database, Eye, Wrench, MessageSquare, History, ChevronLeft, ChevronRight } from 'lucide-react';
import { motion } from 'framer-motion';
import { cn } from '../../utils/cn';
import { ActionSteps } from '../chat/ActionSteps';
import { ReactiveBeanieOrb } from '../presence/ReactiveBeanieOrb';
import { BEANIE_STATES } from '../../design/tokens';
import type { ActionStep, Message } from '../../types';

/**
 * ContextPanel — Beanie's cognitive dashboard (21t review: the reference's
 * right panel is the agent's mind at a glance, not task metadata).
 *
 * Current Goal → State → Focus → Relevant Memory → Perception → Active Tools
 * → Current Chat → Recent Activity → Beanie insight (the light at the bottom).
 *
 * Quiet sections, not cards: the conversation stays the dominant surface; this
 * rail answers "what is Beanie doing, thinking, seeing, and using?" — every
 * section flows from real stores, nothing is decorative.
 *
 * One product, three shells: the desktop Live Context rail shows the same
 * concepts at command-center density; Android reveals them progressively.
 */
export function ContextPanel() {
  const { presence } = usePresenceStore();
  const memories = useMemoryBrowserStore((s) => s.memories);
  const currentConversation = useConversationStore((s) => s.currentConversation);
  const { contextPanelCollapsed, toggleContextPanel } = useLayoutStore();
  const { isCapturing, isStreaming, currentScreenshot, screenshots } = useScreenshotStore();
  const { llmModels, selectedLLM } = useModelSettingsStore();
  const language = useSettingsStore((s) => s.language);

  const collapsed = contextPanelCollapsed;

  // Relevant memory: importance-ranked, top three.
  const relevantMemories = useMemo(
    () => [...memories].sort((a, b) => (b.metadata?.importance ?? 0) - (a.metadata?.importance ?? 0)).slice(0, 3),
    [memories],
  );

  // The execution timeline of the latest message that has steps.
  const latestSteps = useMemo(() => {
    const msgs = currentConversation?.messages ?? [];
    for (let i = msgs.length - 1; i >= 0; i -= 1) {
      const steps = msgs[i].actionSteps;
      if (steps?.length) return steps;
    }
    return [] as ActionStep[];
  }, [currentConversation]);

  // Active tools: what is running or queued right now.
  const activeSteps = useMemo(
    () => latestSteps.filter((s) => s.status === 'in_progress' || s.status === 'pending').slice(-4),
    [latestSteps],
  );

  // Recent activity: the last few events in this conversation.
  const recentEvents = useMemo(() => {
    const msgs = currentConversation?.messages ?? [];
    return msgs.slice(-3).reverse();
  }, [currentConversation]);

  const stateSpec = BEANIE_STATES[presence.status] ?? BEANIE_STATES.idle;
  const screenState = isStreaming ? 'Streaming' : isCapturing ? 'Capturing' : 'Idle';
  const llmName = llmModels.find((m) => m.id === selectedLLM)?.name ?? selectedLLM;
  const messages = currentConversation?.messages ?? [];

  return (
    <motion.aside
      initial={{ x: 20, opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
      aria-label="Context panel"
      className={cn(
        'bg-background-panel border-l border-border-subtle overflow-y-auto transition-all duration-300',
        collapsed ? 'w-16' : 'w-80'
      )}
    >
      <div className={cn('p-4 space-y-6', collapsed && 'px-2 space-y-4')}>

        {/* Current Goal — what Beanie is driving toward */}
        <Section icon={Target} title="Current Goal" collapsed={collapsed}>
          {presence.currentGoal ? (
            <p className="text-sm text-text-primary">{presence.currentGoal}</p>
          ) : (
            <p className="text-sm text-text-muted italic">No active goal</p>
          )}
          {presence.progress !== undefined && (
            <div className="w-full bg-background-surface rounded-full h-2 mt-2" data-tutorial="goal-progress">
              <div
                className="bg-accent-primary h-2 rounded-full transition-all duration-300"
                style={{ width: `${Math.round(presence.progress * 100)}%` }}
                role="progressbar"
                aria-valuenow={Math.round(presence.progress * 100)}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-label="Goal progress"
              />
            </div>
          )}
        </Section>

        {/* State — status + current activity */}
        <Section icon={Activity} title="State" collapsed={collapsed}>
          <div className="flex items-center gap-2">
            <span
              className="w-2 h-2 rounded-full flex-shrink-0"
              style={{ backgroundColor: stateSpec.color }}
              aria-hidden="true"
            />
            <p className="text-sm text-text-primary">{stateSpec.label}</p>
          </div>
          {presence.currentTask && (
            <p className="text-xs text-text-muted mt-1">{presence.currentTask}</p>
          )}
        </Section>

        {/* Focus — the one thing Beanie is on right now */}
        <Section icon={Crosshair} title="Focus" collapsed={collapsed}>
          {presence.currentTask ? (
            <p className="text-sm text-text-primary">{presence.currentTask}</p>
          ) : (
            <p className="text-sm text-text-muted italic">Unfocused</p>
          )}
        </Section>

        {/* Relevant Memory — importance-ranked */}
        <Section icon={Database} title="Relevant Memory" collapsed={collapsed}>
          {relevantMemories.length > 0 ? (
            <div className="space-y-1.5">
              {relevantMemories.map((memory) => (
                <div key={memory.id} className="flex items-baseline gap-2">
                  <span
                    className="w-1.5 h-1.5 rounded-full bg-accent-secondary flex-shrink-0 self-center"
                    style={{ opacity: 0.4 + 0.6 * ((memory.metadata?.importance ?? 5) / 10) }}
                    aria-hidden="true"
                  />
                  <p className="text-sm text-text-primary truncate flex-1">{memory.title}</p>
                </div>
              ))}
              <p className="text-xs text-text-muted">{memories.length} memories</p>
            </div>
          ) : (
            <p className="text-sm text-text-muted italic">No memories yet</p>
          )}
        </Section>

        {/* Perception — screen, vision, environment */}
        <Section icon={Eye} title="Perception" collapsed={collapsed}>
          <dl className="space-y-1 text-sm">
            <div className="flex justify-between gap-2">
              <dt className="text-text-muted">Screen</dt>
              <dd className="text-text-primary">{screenState}</dd>
            </div>
            <div className="flex justify-between gap-2">
              <dt className="text-text-muted">Vision</dt>
              <dd className="text-text-primary truncate" title={currentScreenshot?.analysis?.prompt_focus}>
                {currentScreenshot?.analysis ? 'Active' : 'Not active'}
              </dd>
            </div>
            <div className="flex justify-between gap-2">
              <dt className="text-text-muted">Environment</dt>
              <dd className="text-text-primary truncate" title={llmName}>
                {llmName || '—'}{language ? ` · ${language}` : ''}
              </dd>
            </div>
          </dl>
          {screenshots.length > 0 && (
            <p className="text-xs text-text-muted mt-1">{screenshots.length} captures</p>
          )}
        </Section>

        {/* Active Tools — what is running now */}
        <Section icon={Wrench} title="Active Tools" collapsed={collapsed}>
          {activeSteps.length > 0 ? (
            <ActionSteps steps={activeSteps} />
          ) : (
            <p className="text-sm text-text-muted italic">Quiet</p>
          )}
        </Section>

        {/* Current Chat — where the conversation is happening */}
        <Section icon={MessageSquare} title="Current Chat" collapsed={collapsed}>
          {currentConversation ? (
            <>
              <p className="text-sm text-text-primary truncate">{currentConversation.title}</p>
              <p className="text-xs text-text-muted mt-0.5">
                {messages.length} {messages.length === 1 ? 'message' : 'messages'}
              </p>
            </>
          ) : (
            <p className="text-sm text-text-muted italic">No conversation</p>
          )}
        </Section>

        {/* Recent Activity — the last few events */}
        <Section icon={History} title="Recent Activity" collapsed={collapsed}>
          {recentEvents.length > 0 ? (
            <ol className="space-y-1.5 list-none p-0 m-0">
              {recentEvents.map((event) => (
                <RecentEvent key={event.id} event={event} />
              ))}
            </ol>
          ) : (
            <p className="text-sm text-text-muted italic">Nothing yet</p>
          )}
        </Section>

        {/* Beanie insight — the light at the bottom */}
        {!collapsed && (
          <section
            aria-label="Beanie insight"
            className="rounded-xl bg-accent-primary/10 border border-border-subtle p-3 flex items-start gap-3"
          >
            <ReactiveBeanieOrb status={presence.status} size="sm" />
            <div className="flex-1 min-w-0">
              <p className="text-xs font-semibold bg-beanie-gradient bg-clip-text text-transparent">Beanie</p>
              <p className="text-sm text-text-secondary mt-0.5">{presence.message ?? "I'm here."}</p>
            </div>
          </section>
        )}
      </div>

      {/* Collapse toggle */}
      <div className="p-2 border-t border-border-subtle">
        <button
          onClick={toggleContextPanel}
          className="w-full flex items-center justify-center p-2 rounded-lg text-text-muted hover:text-text-primary hover:bg-background-surface transition-colors"
          aria-label={collapsed ? 'Expand context panel' : 'Collapse context panel'}
        >
          {collapsed ? (
            <ChevronLeft className="w-5 h-5" />
          ) : (
            <>
              <ChevronRight className="w-5 h-5" />
              <span className="ml-2 text-sm">Collapse</span>
            </>
          )}
        </button>
      </div>
    </motion.aside>
  );
}

/** One line of recent activity: who acted, and what happened. */
function RecentEvent({ event }: { event: Message }) {
  const isUser = event.role === 'user';
  const summary =
    event.actionSteps?.length
      ? event.actionSteps.map((s) => s.description).join(', ')
      : event.content.split('\n')[0].slice(0, 60) || '—';
  return (
    <li className="flex items-baseline gap-2">
      <span
        className={cn(
          'text-[10px] font-semibold uppercase tracking-wide flex-shrink-0',
          isUser ? 'text-accent-primary' : 'text-accent-secondary',
        )}
      >
        {isUser ? 'You' : 'Beanie'}
      </span>
      <span className="text-sm text-text-secondary truncate flex-1" title={summary}>{summary}</span>
    </li>
  );
}

interface SectionProps {
  icon: typeof Target;
  title: string;
  collapsed: boolean;
  children: ReactNode;
}

/** Quiet section: small icon + muted uppercase label, content beneath. */
function Section({ icon: Icon, title, collapsed, children }: SectionProps) {
  return (
    <section aria-label={title}>
      <div className="flex items-center gap-2 mb-2">
        <Icon className="w-4 h-4 text-accent-primary flex-shrink-0" aria-hidden="true" />
        {!collapsed && (
          <h3 className="text-xs font-semibold uppercase tracking-wide text-text-muted">{title}</h3>
        )}
      </div>
      {!collapsed && children}
    </section>
  );
}
