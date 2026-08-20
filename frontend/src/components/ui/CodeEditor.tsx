import { useState, useRef, useEffect } from 'react';
import { Play, Save, Trash2, Copy, Check } from 'lucide-react';
import { Button } from './Button';

interface CodeEditorProps {
  code: string;
  language: string;
  onChange?: (code: string) => void;
  onExecute?: (code: string, language: string) => void;
  onSave?: (code: string, language: string) => void;
  onDelete?: () => void;
  readOnly?: boolean;
  showActions?: boolean;
  title?: string;
}

const SUPPORTED_LANGUAGES = [
  { value: 'python', label: 'Python' },
  { value: 'javascript', label: 'JavaScript' },
  { value: 'typescript', label: 'TypeScript' },
  { value: 'bash', label: 'Bash' },
  { value: 'json', label: 'JSON' },
  { value: 'yaml', label: 'YAML' },
  { value: 'markdown', label: 'Markdown' },
  { value: 'text', label: 'Plain Text' },
];

export function CodeEditor({
  code,
  language,
  onChange,
  onExecute,
  onSave,
  onDelete,
  readOnly = false,
  showActions = true,
  title,
}: CodeEditorProps) {
  const [localCode, setLocalCode] = useState(code);
  const [localLanguage, setLocalLanguage] = useState(language);
  const [copied, setCopied] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    setLocalCode(code);
  }, [code]);

  useEffect(() => {
    setLocalLanguage(language);
  }, [language]);

  const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const newCode = e.target.value;
    setLocalCode(newCode);
    onChange?.(newCode);
  };

  const handleLanguageChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const newLanguage = e.target.value;
    setLocalLanguage(newLanguage);
  };

  const handleExecute = () => {
    onExecute?.(localCode, localLanguage);
  };

  const handleSave = () => {
    onSave?.(localCode, localLanguage);
  };

  const handleCopy = async () => {
    await navigator.clipboard.writeText(localCode);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    // Tab key inserts spaces instead of changing focus
    if (e.key === 'Tab') {
      e.preventDefault();
      const start = e.currentTarget.selectionStart;
      const end = e.currentTarget.selectionEnd;
      const newCode = localCode.substring(0, start) + '  ' + localCode.substring(end);
      setLocalCode(newCode);
      onChange?.(newCode);

      // Move cursor after inserted spaces
      setTimeout(() => {
        if (textareaRef.current) {
          textareaRef.current.selectionStart = textareaRef.current.selectionEnd = start + 2;
        }
      }, 0);
    }

    // Ctrl/Cmd + Enter to execute
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      e.preventDefault();
      handleExecute();
    }

    // Ctrl/Cmd + S to save
    if ((e.ctrlKey || e.metaKey) && e.key === 's') {
      e.preventDefault();
      handleSave();
    }
  };

  return (
    <div className="border border-border rounded-lg overflow-hidden bg-background-surface">
      {/* Header */}
      {showActions && (
        <div className="flex items-center justify-between px-4 py-2 bg-background-primary border-b border-border">
          <div className="flex items-center gap-3">
            {title && <span className="text-sm font-medium text-text-primary">{title}</span>}
            <select
              value={localLanguage}
              onChange={handleLanguageChange}
              disabled={readOnly}
              className="px-2 py-1 text-xs bg-background-surface border border-border rounded focus:outline-none focus:ring-2 focus:ring-accent-primary"
            >
              {SUPPORTED_LANGUAGES.map((lang) => (
                <option key={lang.value} value={lang.value}>
                  {lang.label}
                </option>
              ))}
            </select>
          </div>

          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              size="sm"
              onClick={handleCopy}
              title="Copy code"
            >
              {copied ? <Check className="w-4 h-4 text-accent-success" /> : <Copy className="w-4 h-4" />}
            </Button>

            {!readOnly && (
              <>
                {onSave && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={handleSave}
                    title="Save (Ctrl+S)"
                  >
                    <Save className="w-4 h-4" />
                  </Button>
                )}

                {onDelete && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={onDelete}
                    title="Delete"
                  >
                    <Trash2 className="w-4 h-4 text-accent-error" />
                  </Button>
                )}

                {onExecute && (
                  <Button
                    variant="primary"
                    size="sm"
                    onClick={handleExecute}
                    title="Execute (Ctrl+Enter)"
                  >
                    <Play className="w-4 h-4 mr-1" />
                    Run
                  </Button>
                )}
              </>
            )}
          </div>
        </div>
      )}

      {/* Editor */}
      <textarea
        ref={textareaRef}
        value={localCode}
        onChange={handleChange}
        onKeyDown={handleKeyDown}
        readOnly={readOnly}
        className="w-full h-96 p-4 bg-background-surface text-text-primary font-mono text-sm resize-none focus:outline-none"
        spellCheck={false}
        placeholder={readOnly ? '' : 'Enter your code here...'}
      />

      {/* Footer */}
      {showActions && (
        <div className="flex items-center justify-between px-4 py-2 bg-background-primary border-t border-border text-xs text-text-muted">
          <span>{localLanguage}</span>
          <span>{localCode.split('\n').length} lines</span>
        </div>
      )}
    </div>
  );
}
