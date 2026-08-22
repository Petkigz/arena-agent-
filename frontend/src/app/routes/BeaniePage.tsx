import { ReactiveBeanieOrb } from '../../components/presence/ReactiveBeanieOrb';
import { usePresenceStore } from '../../stores';
import { Button } from '../../components/ui';

export function BeaniePage() {
  const { presence, quickActions } = usePresenceStore();

  return (
    <div className="h-full flex flex-col items-center justify-center p-6 bg-background-primary">
      {/* Presence orb */}
      <ReactiveBeanieOrb status={presence.status} size="lg" className="mb-8" />

      {/* Name and status */}
      <h1 className="text-3xl font-bold text-text-primary mb-2">BEANIE</h1>
      <p className="text-text-secondary mb-2">Personal AI</p>
      <p className="text-text-muted italic mb-8">{presence.message}</p>

      {/* Current context */}
      {presence.currentTask && (
        <div className="w-full max-w-md mb-8 p-4 bg-background-secondary rounded-lg">
          <h3 className="text-sm font-semibold text-text-secondary mb-2">Current Context</h3>
          <p className="text-text-primary mb-1">
            <span className="text-text-muted">Working on:</span> {presence.currentTask}
          </p>
          {presence.currentGoal && (
            <p className="text-text-primary mb-1">
              <span className="text-text-muted">Goal:</span> {presence.currentGoal}
            </p>
          )}
          {presence.progress !== undefined && (
            <div className="mt-2">
              <div className="flex justify-between text-sm mb-1">
                <span className="text-text-muted">Progress</span>
                <span className="text-text-secondary">{Math.round(presence.progress * 100)}%</span>
              </div>
              <div className="w-full bg-background-surface rounded-full h-2">
                <div
                  className="bg-accent-primary h-2 rounded-full transition-all duration-300"
                  style={{ width: `${presence.progress * 100}%` }}
                />
              </div>
            </div>
          )}
        </div>
      )}

      {/* Quick actions */}
      <div className="w-full max-w-md grid grid-cols-2 gap-3 mb-8">
        {quickActions.map((action) => (
          <Button key={action.id} variant="secondary" className="h-20">
            {action.label}
          </Button>
        ))}
      </div>

      {/* Voice button */}
      <Button size="lg" className="w-full max-w-md">
        🎙 Talk to Beanie
      </Button>
    </div>
  );
}
