import { useNavigate } from 'react-router-dom';
import { PresenceOrb } from '../../components/presence/PresenceOrb';
import { usePresenceStore, useConversationStore } from '../../stores';
import { Button } from '../../components/ui';

export function BeaniePage() {
  const navigate = useNavigate();
  const { presence, quickActions } = usePresenceStore();
  const { createConversation, setCurrentConversation } = useConversationStore();

  const openChat = async () => {
    const id = await createConversation();
    const conversation = useConversationStore.getState().conversations.find((c) => c.id === id);
    setCurrentConversation(conversation || null);
    navigate('/chat');
  };

  return (
    <div className="h-full flex flex-col items-center justify-center p-6 bg-background-primary overflow-y-auto">
      <PresenceOrb status={presence.status} size="lg" className="mb-3" />

      <h1 className="text-3xl font-bold text-text-primary mb-1">BEANIE</h1>
      <p className="text-text-secondary mb-1">Personal AI</p>
      <p className="text-text-muted italic mb-7">{presence.message}</p>

      {presence.currentTask && (
        <div className="w-full max-w-md mb-7 p-4 bg-background-secondary rounded-xl border border-background-surface">
          <h3 className="text-sm font-semibold text-text-secondary mb-2">Current Context</h3>
          <p className="text-text-primary mb-1"><span className="text-text-muted">Working on:</span> {presence.currentTask}</p>
          {presence.currentGoal && <p className="text-text-primary mb-1"><span className="text-text-muted">Goal:</span> {presence.currentGoal}</p>}
          {presence.progress !== undefined && (
            <div className="mt-3">
              <div className="flex justify-between text-sm mb-1"><span className="text-text-muted">Progress</span><span className="text-text-secondary">{Math.round(presence.progress * 100)}%</span></div>
              <div className="w-full bg-background-surface rounded-full h-2"><div className="bg-accent-primary h-2 rounded-full transition-all duration-300" style={{ width: `${presence.progress * 100}%` }} /></div>
            </div>
          )}
        </div>
      )}

      <div className="w-full max-w-md grid grid-cols-2 gap-3 mb-6">
        {quickActions.map((action) => (
          <Button key={action.id} variant="secondary" className="h-20" onClick={openChat}>{action.label}</Button>
        ))}
      </div>

      <Button size="lg" className="w-full max-w-md" onClick={openChat}>Talk to Beanie</Button>
    </div>
  );
}
