import { useMemo } from 'react';
import type { ReactNode } from 'react';
import { usePresenceStore, useMemoryBrowserStore, useConversationStore, useProjectStore, useLayoutStore } from '../../stores';
import { Target, FolderGit2, Database, Wrench, ChevronLeft, ChevronRight } from 'lucide-react';
import { motion } from 'framer-motion';
import { cn } from '../../utils/cn';
import { ActionSteps } from '../chat/ActionSteps';

/**
 * ContextPanel — the agent's mind (21l review: "an extension of the agent's
 * mind, not a settings sidebar"). Quiet sections — Mission, Working on,
 * Progress, Memory, Tools — NOT cards: the conversation is the dominant
 * surface; this rail only answers "what is Beanie doing and thinking with?".
 *
 * One product, three shells: the same sections the desktop Live Context rail
 * shows at command-center density and Android reveals progressively (one
 * quiet line + a sheet).
 */
export function ContextPanel() {
  const { presence } = usePresenceStore();
  const memories = useMemoryBrowserStore((s) => s.memories);
  const projects = useProjectStore((s) => s.projects);
  const currentConversation = useConversationStore((s) => s.currentConversation);
  const { contextPanelCollapsed, toggleContextPanel } = useLayoutStore();

  const collapsed = contextPanelCollapsed;
  const recentMemories = memories.slice(0, 3);
  const activeProject = projects.find((p) => p.status === 'active') ?? projects[0];

  // Tools: the latest action steps in this conversation — the execution
  // timeline, rendered with the same semantic icons as the conversation.
  const toolSteps = useMemo(() => {
    const msgs = currentConversation?.messages ?? [];
    for (let i = msgs.length - 1; i >= 0; i -= 1) {
      const steps = msgs[i].actionSteps;
      if (steps?.length) return steps.slice(-4);
    }
    return [];
  }, [currentConversation]);

  return (
    <motion.aside
      initial={{ x: 20, opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
      aria-label="Context panel"
      className={cn(
        'bg-background-secondary border-l border-background-surface overflow-y-auto transition-all duration-300',
        collapsed ? 'w-16' : 'w-80'
      )}
    >
      <div className={cn('p-4 space-y-6', collapsed && 'px-2 space-y-4')}>
        {/* Mission */}
        <Section icon={Target} title="Mission" collapsed={collapsed}>
          {presence.currentGoal ? (
            <p className="text-sm text-text-primary">{presence.currentGoal}</p>
          ) : (
            <p className="text-sm text-text-muted italic">No active mission</p>
          )}
          {presence.currentTask && (
            <p className="text-xs text-text-muted mt-1">
              <span className="font-medium">Task:</span> {presence.currentTask}
            </p>
          )}
        </Section>

        {/* Working on */}
        <Section icon={FolderGit2} title="Working on" collapsed={collapsed}>
          {activeProject ? (
            <>
              <p className="text-sm text-text-primary">{activeProject.name}</p>
              <p className="text-xs text-text-muted mt-0.5 capitalize">{activeProject.status}</p>
            </>
          ) : (
            <p className="text-sm text-text-muted italic">—</p>
          )}
        </Section>

        {/* Progress (only while something is actually in flight) */}
        {presence.progress !== undefined && (
          <Section icon={Target} title="Progress" collapsed={collapsed}>
            <div className="w-full bg-background-surface rounded-full h-2">
              <div
                className="bg-accent-primary h-2 rounded-full transition-all duration-300"
                style={{ width: `${Math.round(presence.progress * 100)}%` }}
                role="progressbar"
                aria-valuenow={Math.round(presence.progress * 100)}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-label="Task progress"
              />
            </div>
          </Section>
        )}

        {/* Memory */}
        <Section icon={Database} title="Memory" collapsed={collapsed}>
          {recentMemories.length > 0 ? (
            <div className="space-y-1.5">
              {recentMemories.map((memory) => (
                <div key={memory.id} className="text-sm text-text-primary truncate">
                  • {memory.title}
                </div>
              ))}
              <p className="text-xs text-text-muted">{memories.length} memories</p>
            </div>
          ) : (
            <p className="text-sm text-text-muted italic">No memories yet</p>
          )}
        </Section>

        {/* Tools — the execution timeline */}
        <Section icon={Wrench} title="Tools" collapsed={collapsed}>
          {toolSteps.length > 0 ? (
            <ActionSteps steps={toolSteps} />
          ) : (
            <p className="text-sm text-text-muted italic">Quiet</p>
          )}
        </Section>
      </div>

      {/* Collapse toggle */}
      <div className="p-2 border-t border-background-surface">
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
