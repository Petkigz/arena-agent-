import type { Attachment } from '../stores/multiModalStore';

export interface Message {
  id: string;
  conversationId?: string;
  /** Runtime-authored trace of this exact assistant response, never the latest turn. */
  traceId?: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
  actionSteps?: ActionStep[];
  reasoningTrace?: string;
  codeChanges?: CodeChange[];
  attachments?: Attachment[];
  status?: 'sending' | 'sent' | 'pending' | 'streaming' | 'complete' | 'error';
}

export interface ActionStep {
  id: string;
  description: string;
  status: 'pending' | 'in_progress' | 'complete' | 'error';
  timestamp?: string;
  details?: string;
}

export interface CodeChange {
  file: string;
  language?: string;
  diff: string;
  description?: string;
}

export interface Conversation {
  id: string;
  title: string;
  messages: Message[];
  createdAt: string;
  updatedAt: string;
  projectId?: string;
  tags?: string[];
}

export interface ConversationListItem {
  id: string;
  title: string;
  lastMessage: string;
  updatedAt: string;
  unread?: boolean;
  projectId?: string;
}

/** Durable server history, including additive response trace links. */
export interface ServerConversationMessage {
  role: string;
  content: string;
  message_id?: string | number;
  trace_id?: string;
  created_at?: string;
}
