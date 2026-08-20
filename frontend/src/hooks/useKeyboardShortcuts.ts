import { useHotkeys } from 'react-hotkeys-hook';
import { useNavigate } from 'react-router-dom';
import { useState } from 'react';
import { useConversationStore, useLayoutStore } from '../stores';

export interface KeyboardShortcut {
  keys: string[];
  description: string;
  action: () => void;
  enabled?: boolean;
}

export function useKeyboardShortcuts() {
  const navigate = useNavigate();
  const { currentConversation, conversations, createConversation, setCurrentConversation } = useConversationStore();
  const { toggleSidebar, toggleContextPanel } = useLayoutStore();
  const [showShortcutsModal, setShowShortcutsModal] = useState(false);

  // Help modal
  useHotkeys('?', () => {
    setShowShortcutsModal(prev => !prev);
  }, { preventDefault: true });

  // Navigation shortcuts
  useHotkeys('ctrl+n', async () => {
    // Create new conversation and navigate to it
    const newId = await createConversation('New Conversation');
    const newConv = conversations.find(c => c.id === newId);
    if (newConv) {
      setCurrentConversation(newConv);
    }
    navigate('/chat');
  }, { preventDefault: true });

  useHotkeys('ctrl+f', () => {
    // Focus search
    const searchInput = document.querySelector('input[placeholder*="Search"]') as HTMLInputElement;
    if (searchInput) {
      searchInput.focus();
    }
  }, { preventDefault: true });

  useHotkeys('ctrl+,', () => {
    // Open settings
    navigate('/settings');
  }, { preventDefault: true });

  useHotkeys('ctrl+1', () => navigate('/chat'), { preventDefault: true });
  useHotkeys('ctrl+2', () => navigate('/pansophy'), { preventDefault: true });
  useHotkeys('ctrl+3', () => navigate('/files'), { preventDefault: true });
  useHotkeys('ctrl+4', () => navigate('/code'), { preventDefault: true });

  // Chat shortcuts
  useHotkeys('ctrl+enter', () => {
    // Send message (when in chat input)
    const sendButton = document.querySelector('button[type="submit"]') as HTMLButtonElement;
    if (sendButton && !sendButton.disabled) {
      sendButton.click();
    }
  }, { preventDefault: true });

  useHotkeys('escape', () => {
    // Close modals, cancel actions
    const closeButton = document.querySelector('[data-close-modal]') as HTMLButtonElement;
    if (closeButton) {
      closeButton.click();
    }
  });

  // Conversation navigation
  useHotkeys('ctrl+up', () => {
    // Previous conversation
    if (currentConversation && conversations.length > 1) {
      const currentIndex = conversations.findIndex(c => c.id === currentConversation.id);
      if (currentIndex > 0) {
        const prevConversation = conversations[currentIndex - 1];
        navigate(`/chat?conversation=${prevConversation.id}`);
      }
    }
  }, { preventDefault: true });

  useHotkeys('ctrl+down', () => {
    // Next conversation
    if (currentConversation && conversations.length > 1) {
      const currentIndex = conversations.findIndex(c => c.id === currentConversation.id);
      if (currentIndex < conversations.length - 1) {
        const nextConversation = conversations[currentIndex + 1];
        navigate(`/chat?conversation=${nextConversation.id}`);
      }
    }
  }, { preventDefault: true });

  // Panel toggle shortcuts
  useHotkeys('ctrl+b', () => {
    toggleSidebar();
  }, { preventDefault: true });

  useHotkeys('ctrl+j', () => {
    toggleContextPanel();
  }, { preventDefault: true });

  // Return list of all shortcuts for help modal
  const shortcuts: KeyboardShortcut[] = [
    { keys: ['Ctrl', 'N'], description: 'New conversation', action: () => {} },
    { keys: ['Ctrl', 'F'], description: 'Search conversations', action: () => {} },
    { keys: ['Ctrl', ','], description: 'Open settings', action: () => {} },
    { keys: ['Ctrl', '1'], description: 'Go to Chat', action: () => {} },
    { keys: ['Ctrl', '2'], description: 'Go to Pansophy', action: () => {} },
    { keys: ['Ctrl', '3'], description: 'Go to Files', action: () => {} },
    { keys: ['Ctrl', '4'], description: 'Go to Code', action: () => {} },
    { keys: ['Ctrl', 'Enter'], description: 'Send message', action: () => {} },
    { keys: ['Esc'], description: 'Close modal / Cancel', action: () => {} },
    { keys: ['Ctrl', '↑'], description: 'Previous conversation', action: () => {} },
    { keys: ['Ctrl', '↓'], description: 'Next conversation', action: () => {} },
    { keys: ['?'], description: 'Show keyboard shortcuts', action: () => {} },
    { keys: ['Ctrl', 'B'], description: 'Toggle sidebar', action: () => {} },
    { keys: ['Ctrl', 'J'], description: 'Toggle context panel', action: () => {} },
  ];

  return { shortcuts, showShortcutsModal, setShowShortcutsModal };
}
