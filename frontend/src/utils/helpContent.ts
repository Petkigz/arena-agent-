/**
 * Help content for Arena - tutorials, FAQs, and documentation
 */

export interface TutorialStep {
  id: string;
  target: string;
  title: string;
  content: string;
  position?: 'top' | 'bottom' | 'left' | 'right';
}

export interface FAQItem {
  question: string;
  answer: string;
}

/**
 * Main tutorial steps for first-time users
 */
export const mainTutorialSteps: TutorialStep[] = [
  {
    id: 'welcome',
    target: '[data-tutorial="presence-orb"]',
    title: 'Welcome to Arena!',
    content: 'This pulsing orb shows Arena\'s status. When it\'s listening, it will glow brighter. You can talk to Arena anytime by saying your wake word.',
    position: 'right',
  },
  {
    id: 'chat-input',
    target: '[data-tutorial="chat-input"]',
    title: 'Chat with Arena',
    content: 'Type your messages here or click the microphone button to use voice input. Press Enter or Ctrl+Enter to send.',
    position: 'top',
  },
  {
    id: 'conversation-list',
    target: '[data-tutorial="conversation-list"]',
    title: 'Your Conversations',
    content: 'Your conversation history, grouped by recency — Today, Yesterday, the previous 7 days, and Older. Click any conversation to open it, or start a new one with the button above.',
    position: 'right',
  },
  {
    id: 'knowledge-graph',
    target: '[data-tutorial="nav-pansophy"]',
    title: 'Knowledge Graph',
    content: 'Explore your knowledge graph here. Arena automatically builds this from your conversations and memories.',
    position: 'right',
  },
  {
    id: 'files',
    target: '[data-tutorial="nav-files"]',
    title: 'File Management',
    content: 'Upload and manage files here. Arena can analyze documents, images, and code files.',
    position: 'right',
  },
  {
    id: 'code-execution',
    target: '[data-tutorial="nav-code"]',
    title: 'Code Execution',
    content: 'Write and execute code in a secure sandbox. Supports Python, JavaScript, TypeScript, and more.',
    position: 'right',
  },
  {
    id: 'settings',
    target: '[data-tutorial="nav-settings"]',
    title: 'Settings',
    content: 'Customize Arena\'s behavior, voice, appearance, and privacy settings here.',
    position: 'right',
  },
  {
    id: 'keyboard-shortcuts',
    target: 'body',
    title: 'Keyboard Shortcuts',
    content: 'Press ? anytime to see all keyboard shortcuts. Use Ctrl+N for new conversation, Ctrl+F to search, and more!',
    position: 'bottom',
  },
];

/**
 * FAQ items
 */
export const faqItems: FAQItem[] = [
  {
    question: 'How do I change the wake word?',
    answer: 'Go to Settings → Voice → Wake Word. You can choose from preset wake words or train a custom one by recording your voice saying the phrase 5 times.',
  },
  {
    question: 'Can Arena remember things across conversations?',
    answer: 'Yes! Arena has a memory system that stores important information you share. You can view and manage memories in the Pansophy section under "Memories".',
  },
  {
    question: 'How does the knowledge graph work?',
    answer: 'The knowledge graph is a visual representation of everything Arena knows. Nodes represent concepts, and edges show relationships. Arena automatically builds this from your conversations, or you can add nodes manually.',
  },
  {
    question: 'Is my data private?',
    answer: 'Yes! All your data is stored locally on your device by default. You can enable cloud sync in Settings → Privacy if you want to access your data across devices. Arena never shares your data with third parties.',
  },
  {
    question: 'Can I use Arena offline?',
    answer: 'Basic chat and knowledge management work offline. However, advanced features like code execution, file analysis, and multi-modal interactions require an internet connection.',
  },
  {
    question: 'How do I export my conversations?',
    answer: 'Click the share icon in the conversation header. You can export as Markdown, Text, or HTML. You can also copy to clipboard or generate a shareable link.',
  },
  {
    question: 'What file types can Arena analyze?',
    answer: 'Arena can analyze images (OCR, vision), documents (PDF, DOCX, XLSX, PPTX), code files (Python, JavaScript, etc.), and text files. Upload files in the Files section or attach them to messages.',
  },
  {
    question: 'How do I pair my phone with Arena?',
    answer: 'Verified QR/code pairing is not implemented yet. Configure the Android app with the authenticated Arena server URL and API key manually; onboarding will not invent a connected device.',
  },
  {
    question: 'Can multiple people use Arena?',
    answer: 'Multiple people can use Arena through separate conversations, but automatic speaker identification is currently unavailable until a verified speaker-embedding engine is installed. Arena will not guess an identity or report a fake confidence score.',
  },
  {
    question: 'How do I reset Arena to default settings?',
    answer: 'Go to Settings → Privacy → Data Management → Reset All Settings. This will reset all preferences but keep your conversations and knowledge graph.',
  },
  {
    question: 'What languages does Arena support?',
    answer: 'Arena currently supports English and Swahili. You can change the language in Settings → Voice → Language. More languages will be added in future updates.',
  },
  {
    question: 'How do I report a bug or request a feature?',
    answer: 'Click the help button (?) in the top-right corner and select "Report Issue" or "Request Feature". You can also check the FAQ first to see if your question has been answered.',
  },
];

/**
 * Keyboard shortcuts reference
 */
export const keyboardShortcuts = [
  { keys: ['Ctrl', 'N'], description: 'New conversation' },
  { keys: ['Ctrl', 'F'], description: 'Search conversations' },
  { keys: ['Ctrl', ','], description: 'Open settings' },
  { keys: ['Ctrl', '1'], description: 'Go to Chat' },
  { keys: ['Ctrl', '2'], description: 'Go to Pansophy' },
  { keys: ['Ctrl', '3'], description: 'Go to Files' },
  { keys: ['Ctrl', '4'], description: 'Go to Code' },
  { keys: ['Ctrl', 'Enter'], description: 'Send message' },
  { keys: ['Esc'], description: 'Close modal / Cancel' },
  { keys: ['Ctrl', '↑'], description: 'Previous conversation' },
  { keys: ['Ctrl', '↓'], description: 'Next conversation' },
  { keys: ['?'], description: 'Show keyboard shortcuts' },
];

/**
 * Tips for better results
 */
export const tips = [
  'Be specific in your requests. Instead of "help me with code", say "help me debug this Python function".',
  'Use the knowledge graph to see what Arena knows about a topic before asking questions.',
  'Attach files directly to messages for instant analysis.',
  'Use voice input for hands-free interaction. Just say your wake word and start talking.',
  'Create projects to organize related conversations and files.',
  'Use keyboard shortcuts to navigate faster. Press ? to see all shortcuts.',
  'Export important conversations as Markdown for documentation.',
  'Train a custom wake word for better accuracy in noisy environments.',
  'Use the memory system to store important information Arena should remember.',
  'Check the action steps in responses to see what Arena is doing.',
];
