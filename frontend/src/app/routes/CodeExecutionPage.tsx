import { useState } from 'react';
import { Plus, Trash2, Code } from 'lucide-react';
import { Button } from '../../components/ui/Button';
import { CodeEditor } from '../../components/ui/CodeEditor';
import { ExecutionResults } from '../../components/ui/ExecutionResults';
import { EmptyState } from '../../components/ui/EmptyState';
import { SkeletonList } from '../../components/ui/SkeletonCard';
import { useCodeStore } from '../../stores/codeStore';

export function CodeExecutionPage() {
  const {
    sessions,
    currentSession,
    currentSnippet,
    createSession,
    deleteSession,
    setCurrentSession,
    addSnippet,
    updateSnippet,
    deleteSnippet,
    setCurrentSnippet,
    executeSnippet,
    isExecuting,
  } = useCodeStore();

  const [code, setCode] = useState('');
  const [language, setLanguage] = useState('python');

  const handleCreateSession = () => {
    createSession();
  };

  const handleDeleteSession = (id: string) => {
    if (confirm('Delete this session and all its snippets?')) {
      deleteSession(id);
    }
  };

  const handleAddSnippet = () => {
    const title = prompt('Snippet title:', 'Untitled Snippet');
    if (title) {
      addSnippet({
        title,
        language: 'python',
        code: '',
      });
    }
  };

  const handleDeleteSnippet = (id: string) => {
    if (confirm('Delete this snippet?')) {
      deleteSnippet(id);
    }
  };

  const handleSelectSnippet = (snippetId: string) => {
    const snippet = currentSession?.snippets.find((s) => s.id === snippetId);
    if (snippet) {
      setCurrentSnippet(snippet);
      setCode(snippet.code);
      setLanguage(snippet.language);
    }
  };

  const handleCodeChange = (newCode: string) => {
    setCode(newCode);
    if (currentSnippet) {
      updateSnippet(currentSnippet.id, { code: newCode });
    }
  };

  const handleExecute = async (_codeToRun: string, _lang: string) => {
    if (!currentSnippet) return;
    
    await executeSnippet(currentSnippet.id);
  };

  const handleSave = (codeToSave: string, lang: string) => {
    if (currentSnippet) {
      updateSnippet(currentSnippet.id, { code: codeToSave, language: lang });
      alert('Snippet saved!');
    }
  };

  return (
    <div className="h-full flex flex-col bg-background-primary">
      {/* Header */}
      <div className="flex-shrink-0 px-6 py-4 border-b border-border">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-text-primary">Code Execution</h1>
            <p className="text-text-secondary mt-1">Write and execute code in a secure sandbox</p>
          </div>
          <Button variant="primary" onClick={handleCreateSession}>
            <Plus className="w-4 h-4 mr-2" />
            New Session
          </Button>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 flex overflow-hidden">
        {/* Sidebar - Sessions and Snippets */}
        <div className="w-64 border-r border-border overflow-y-auto bg-background-secondary">
          {sessions.length === 0 ? (
            <EmptyState
              icon={<Code className="w-12 h-12" />}
              title="No sessions yet"
              description="Create a session to get started"
              className="p-4"
            />
          ) : (
            <div className="p-2 space-y-2">
              {sessions.map((session) => (
                <div key={session.id} className="space-y-1">
                  {/* Session header */}
                  <div
                    className={`flex items-center justify-between p-2 rounded cursor-pointer ${
                      currentSession?.id === session.id
                        ? 'bg-accent-primary/20 text-accent-primary'
                        : 'hover:bg-background-surface text-text-secondary'
                    }`}
                    onClick={() => setCurrentSession(session)}
                  >
                    <span className="text-sm font-medium truncate">{session.name}</span>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        handleDeleteSession(session.id);
                      }}
                      className="opacity-0 group-hover:opacity-100 hover:text-accent-error"
                    >
                      <Trash2 className="w-3 h-3" />
                    </button>
                  </div>

                  {/* Snippets */}
                  {currentSession?.id === session.id && (
                    <div className="ml-3 space-y-1">
                      {session.snippets.map((snippet) => (
                        <div
                          key={snippet.id}
                          className={`flex items-center justify-between p-2 rounded cursor-pointer text-xs ${
                            currentSnippet?.id === snippet.id
                              ? 'bg-background-surface text-text-primary'
                              : 'hover:bg-background-surface/50 text-text-muted'
                          }`}
                          onClick={() => handleSelectSnippet(snippet.id)}
                        >
                          <span className="truncate">{snippet.title}</span>
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              handleDeleteSnippet(snippet.id);
                            }}
                            className="opacity-0 group-hover:opacity-100 hover:text-accent-error"
                          >
                            <Trash2 className="w-3 h-3" />
                          </button>
                        </div>
                      ))}

                      <button
                        onClick={handleAddSnippet}
                        className="w-full p-2 text-xs text-text-muted hover:text-text-primary hover:bg-background-surface rounded"
                      >
                        + Add Snippet
                      </button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Main content - Editor and Results */}
        <div className="flex-1 flex flex-col overflow-hidden">
          {currentSnippet ? (
            <div className="flex-1 overflow-y-auto p-6 space-y-6">
              {/* Code Editor */}
              <CodeEditor
                code={code}
                language={language}
                onChange={handleCodeChange}
                onExecute={handleExecute}
                onSave={handleSave}
                onDelete={() => handleDeleteSnippet(currentSnippet.id)}
                title={currentSnippet.title}
              />

        {/* Execution Results */}
        {currentSnippet.executionResult && (
          <ExecutionResults result={currentSnippet.executionResult} />
        )}
        
        {/* Loading indicator */}
        {isExecuting && (
          <div className="flex items-center justify-center py-8">
            <div className="text-center">
              <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-accent-primary mx-auto"></div>
              <p className="mt-4 text-text-secondary">Executing code in sandbox...</p>
            </div>
          </div>
        )}
            </div>
          ) : (
            <div className="flex-1 flex items-center justify-center text-text-muted">
              <div className="text-center">
                <p className="text-lg mb-2">No snippet selected</p>
                <p className="text-sm">Select a snippet from the sidebar or create a new one</p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
