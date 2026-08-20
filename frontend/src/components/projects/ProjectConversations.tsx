import { useNavigate } from 'react-router-dom';
import type { Project } from '../../stores/projectStore';
import { MessageCircle } from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';

interface ProjectConversationsProps {
  project: Project;
}

export function ProjectConversations({ project }: ProjectConversationsProps) {
  const navigate = useNavigate();

  const handleOpenConversation = (conversationId: string) => {
    navigate(`/chat?conversation=${conversationId}`);
  };

  if (project.conversations.length === 0) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center">
          <MessageCircle className="w-16 h-16 text-text-muted mx-auto mb-4" />
          <h3 className="text-lg font-semibold text-text-primary mb-2">No conversations yet</h3>
          <p className="text-text-secondary">
            Conversations linked to this project will appear here
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6">
      <div className="space-y-2">
        {project.conversations.map((conversation) => (
          <div
            key={conversation.id}
            onClick={() => handleOpenConversation(conversation.id)}
            className="flex items-center gap-4 p-4 bg-background-surface border border-border rounded-lg hover:border-accent-primary transition-colors cursor-pointer"
          >
            <div className="w-10 h-10 bg-accent-primary/10 rounded-lg flex items-center justify-center flex-shrink-0">
              <MessageCircle className="w-5 h-5 text-accent-primary" />
            </div>

            <div className="flex-1 min-w-0">
              <h4 className="font-medium text-text-primary truncate">{conversation.title}</h4>
              <div className="flex items-center gap-3 text-sm text-text-muted mt-1">
                <span>{conversation.messageCount} messages</span>
                <span>•</span>
                <span>{formatDistanceToNow(new Date(conversation.lastActivity), { addSuffix: true })}</span>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
