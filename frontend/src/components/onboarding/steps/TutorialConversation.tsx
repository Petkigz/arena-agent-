import { useState } from 'react';
import { Button } from '../../ui/Button';
import { MessageCircle, ArrowRight, ArrowLeft, SkipForward, Send, Bot, User } from 'lucide-react';

interface TutorialConversationProps {
  onNext: () => void;
  onBack: () => void;
  onSkip: () => void;
}

interface TutorialMessage {
  role: 'user' | 'assistant';
  content: string;
  isExample?: boolean;
}

export function TutorialConversation({ onNext, onBack, onSkip }: TutorialConversationProps) {
  const [messages, setMessages] = useState<TutorialMessage[]>([
    {
      role: 'assistant',
      content: "Hi! I'm Arena, your personal AI assistant. Let me show you what I can do. Try sending me a message below!",
    },
  ]);
  const [inputValue, setInputValue] = useState('');
  const [currentTutorialStep, setCurrentTutorialStep] = useState(0);

  const tutorialSteps = [
    {
      prompt: "Try asking: \"What can you do?\"",
      expectedKeywords: ['what', 'can', 'do'],
      response: "I can help you with many things! I can:\n\n• **Chat** - Have natural conversations with voice or text\n• **Manage knowledge** - Build a visual knowledge graph\n• **Execute code** - Run Python, JavaScript, and more\n• **Analyze files** - Upload and analyze documents\n• **Remember things** - Store and recall memories\n\nWhat would you like to try first?",
    },
    {
      prompt: "Try asking: \"Remember that I prefer dark mode\"",
      expectedKeywords: ['remember', 'dark', 'mode'],
      response: "Got it! I've saved that to my memory. You prefer dark mode. I'll remember this for our future conversations. You can view all your memories in the Pansophy section.",
    },
    {
      prompt: "Try asking: \"Show me my knowledge graph\"",
      expectedKeywords: ['knowledge', 'graph', 'show'],
      response: "Your knowledge graph is in the Pansophy section (Ctrl+2). It's a visual representation of everything I know. You can add nodes, create connections, and explore relationships between concepts.",
    },
  ];

  const handleSendMessage = () => {
    if (!inputValue.trim()) return;

    const userMessage: TutorialMessage = {
      role: 'user',
      content: inputValue,
    };

    setMessages(prev => [...prev, userMessage]);
    setInputValue('');

    // Check if this matches the current tutorial step
    const currentStep = tutorialSteps[currentTutorialStep];
    const inputLower = inputValue.toLowerCase();
    const matchesStep = currentStep?.expectedKeywords.some(keyword => 
      inputLower.includes(keyword)
    );

    // Generate response
    setTimeout(() => {
      let response: string;
      
      if (matchesStep && currentStep) {
        response = currentStep.response;
        setCurrentTutorialStep(prev => prev + 1);
      } else {
        response = "That's a great question! In the full version of Arena, I would process this using my cognitive engine and give you a detailed response. For now, try following the tutorial prompts to see what I can do.";
      }

      const assistantMessage: TutorialMessage = {
        role: 'assistant',
        content: response,
      };

      setMessages(prev => [...prev, assistantMessage]);
    }, 1000);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  const progress = (currentTutorialStep / tutorialSteps.length) * 100;

  return (
    <div className="max-w-3xl mx-auto px-6 py-12">
      {/* Header */}
      <div className="text-center mb-8">
        <div className="inline-flex items-center justify-center w-20 h-20 bg-accent-primary/10 rounded-full mb-6">
          <MessageCircle className="w-10 h-10 text-accent-primary" />
        </div>
        <h2 className="text-3xl font-bold text-text-primary mb-3">
          Try Arena
        </h2>
        <p className="text-text-secondary">
          Let's have a quick conversation to see how Arena works
        </p>
      </div>

      {/* Progress */}
      <div className="mb-6">
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm text-text-secondary">
            Tutorial: {currentTutorialStep} of {tutorialSteps.length}
          </span>
          <span className="text-sm text-text-secondary">{Math.round(progress)}%</span>
        </div>
        <div className="h-2 bg-background-surface rounded-full overflow-hidden">
          <div
            className="h-full bg-accent-primary transition-all duration-300"
            style={{ width: `${progress}%` }}
          />
        </div>
      </div>

      {/* Tutorial hint */}
      {currentTutorialStep < tutorialSteps.length && (
        <div className="mb-6 p-4 bg-accent-primary/10 border border-accent-primary/30 rounded-lg">
          <p className="text-sm text-accent-primary font-medium">
            💡 {tutorialSteps[currentTutorialStep].prompt}
          </p>
        </div>
      )}

      {/* Chat interface */}
      <div className="bg-background-secondary rounded-lg overflow-hidden mb-6">
        {/* Messages */}
        <div className="h-96 overflow-y-auto p-6 space-y-4">
          {messages.map((message, index) => (
            <div
              key={index}
              className={`flex items-start gap-3 ${
                message.role === 'user' ? 'flex-row-reverse' : ''
              }`}
            >
              {/* Avatar */}
              <div
                className={`flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center ${
                  message.role === 'assistant'
                    ? 'bg-accent-primary'
                    : 'bg-background-surface'
                }`}
              >
                {message.role === 'assistant' ? (
                  <Bot className="w-5 h-5 text-white" />
                ) : (
                  <User className="w-5 h-5 text-text-primary" />
                )}
              </div>

              {/* Message bubble */}
              <div
                className={`flex-1 max-w-[80%] ${
                  message.role === 'user' ? 'text-right' : ''
                }`}
              >
                <div
                  className={`inline-block px-4 py-2 rounded-2xl ${
                    message.role === 'assistant'
                      ? 'bg-background-surface text-text-primary'
                      : 'bg-accent-primary text-white'
                  }`}
                >
                  <p className="text-sm whitespace-pre-wrap">{message.content}</p>
                </div>
              </div>
            </div>
          ))}
        </div>

        {/* Input */}
        <div className="border-t border-border p-4">
          <div className="flex gap-2">
            <input
              type="text"
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Type a message..."
              className="flex-1 px-4 py-2 bg-background-primary border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-accent-primary"
            />
            <Button
              onClick={handleSendMessage}
              disabled={!inputValue.trim()}
              size="sm"
            >
              <Send className="w-4 h-4" />
            </Button>
          </div>
        </div>
      </div>

      {/* Tips */}
      <div className="bg-background-secondary/50 rounded-lg p-6 mb-8">
        <h3 className="font-semibold text-text-primary mb-3">What you just experienced:</h3>
        <ul className="space-y-2 text-sm text-text-secondary">
          <li className="flex items-start gap-2">
            <span className="text-accent-primary mt-0.5">•</span>
            <span><strong>Natural conversation</strong> - Arena understands context and responds intelligently</span>
          </li>
          <li className="flex items-start gap-2">
            <span className="text-accent-primary mt-0.5">•</span>
            <span><strong>Memory</strong> - Arena remembers things you tell it across conversations</span>
          </li>
          <li className="flex items-start gap-2">
            <span className="text-accent-primary mt-0.5">•</span>
            <span><strong>Knowledge graph</strong> - Visual representation of everything Arena knows</span>
          </li>
          <li className="flex items-start gap-2">
            <span className="text-accent-primary mt-0.5">•</span>
            <span><strong>Voice interaction</strong> - You can also talk to Arena using your voice</span>
          </li>
        </ul>
      </div>

      {/* Actions */}
      <div className="flex flex-col gap-3">
        <Button onClick={onNext} size="lg" className="w-full">
          {currentTutorialStep >= tutorialSteps.length ? 'Finish Setup' : 'Continue'}
          <ArrowRight className="w-5 h-5 ml-2" />
        </Button>

        <div className="flex gap-3">
          <Button onClick={onBack} variant="secondary" size="lg" className="flex-1">
            <ArrowLeft className="w-5 h-5 mr-2" />
            Back
          </Button>

          <button
            onClick={onSkip}
            className="flex items-center justify-center gap-2 text-text-muted hover:text-text-secondary transition-colors flex-1"
          >
            <SkipForward className="w-4 h-4" />
            <span className="text-sm">Skip tutorial</span>
          </button>
        </div>
      </div>
    </div>
  );
}
