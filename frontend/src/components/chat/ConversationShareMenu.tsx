import { useState } from 'react';
import { Button } from '../ui/Button';
import { Modal } from '../ui/Modal';
import type { Conversation } from '../../types';
import {
  conversationToMarkdown,
  conversationToText,
  conversationToHTML,
  downloadFile,
  copyToClipboard,
  generateShareableLink,
  shareViaEmail,
  shareViaWebAPI,
} from '../../services/conversationExport';
import { Share2, FileText, FileDown, Mail, Link, Copy, Check } from 'lucide-react';
import toast from 'react-hot-toast';

interface ConversationShareMenuProps {
  conversation: Conversation;
  isOpen: boolean;
  onClose: () => void;
}

export function ConversationShareMenu({ conversation, isOpen, onClose }: ConversationShareMenuProps) {
  const [copied, setCopied] = useState(false);
  const [shareableLink, setShareableLink] = useState<string>('');
  const [isGeneratingLink, setIsGeneratingLink] = useState(false);

  const handleExportMarkdown = () => {
    const markdown = conversationToMarkdown(conversation);
    const filename = `${conversation.title.replace(/[^a-z0-9]/gi, '_')}.md`;
    downloadFile(markdown, filename, 'text/markdown');
    toast.success('Exported as Markdown');
    onClose();
  };

  const handleExportText = () => {
    const text = conversationToText(conversation);
    const filename = `${conversation.title.replace(/[^a-z0-9]/gi, '_')}.txt`;
    downloadFile(text, filename, 'text/plain');
    toast.success('Exported as Text');
    onClose();
  };

  const handleExportHTML = () => {
    const html = conversationToHTML(conversation);
    const filename = `${conversation.title.replace(/[^a-z0-9]/gi, '_')}.html`;
    downloadFile(html, filename, 'text/html');
    toast.success('Exported as HTML');
    onClose();
  };

  const handleCopyToClipboard = async () => {
    const text = conversationToText(conversation);
    const success = await copyToClipboard(text);
    if (success) {
      setCopied(true);
      toast.success('Copied to clipboard');
      setTimeout(() => setCopied(false), 2000);
    } else {
      toast.error('Failed to copy to clipboard');
    }
  };

  const handleGenerateShareableLink = async () => {
    setIsGeneratingLink(true);
    try {
      const link = await generateShareableLink(conversation.id);
      setShareableLink(link);
      const success = await copyToClipboard(link);
      if (success) {
        toast.success('Shareable link generated and copied');
      } else {
        toast.success('Shareable link generated');
      }
    } catch {
      toast.error('Failed to generate shareable link');
    } finally {
      setIsGeneratingLink(false);
    }
  };

  const handleShareViaEmail = () => {
    shareViaEmail(conversation);
    onClose();
  };

  const handleShareViaWebAPI = async () => {
    const success = await shareViaWebAPI(conversation);
    if (!success) {
      toast.error('Web Share API not supported in this browser');
    }
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Share Conversation">
      <div className="space-y-4">
        {/* Export options */}
        <div>
          <h3 className="text-sm font-medium text-text-primary mb-3">Export As</h3>
          <div className="grid grid-cols-3 gap-2">
            <Button onClick={handleExportMarkdown} variant="secondary" size="sm">
              <FileText className="w-4 h-4 mr-2" />
              Markdown
            </Button>
            <Button onClick={handleExportText} variant="secondary" size="sm">
              <FileDown className="w-4 h-4 mr-2" />
              Text
            </Button>
            <Button onClick={handleExportHTML} variant="secondary" size="sm">
              <FileText className="w-4 h-4 mr-2" />
              HTML
            </Button>
          </div>
        </div>

        {/* Share options */}
        <div>
          <h3 className="text-sm font-medium text-text-primary mb-3">Share</h3>
          <div className="space-y-2">
            {/* Copy to clipboard */}
            <Button onClick={handleCopyToClipboard} variant="secondary" className="w-full">
              {copied ? (
                <>
                  <Check className="w-4 h-4 mr-2" />
                  Copied!
                </>
              ) : (
                <>
                  <Copy className="w-4 h-4 mr-2" />
                  Copy to Clipboard
                </>
              )}
            </Button>

            {/* Shareable link */}
            <Button
              onClick={handleGenerateShareableLink}
              variant="secondary"
              className="w-full"
              disabled={isGeneratingLink}
            >
              <Link className="w-4 h-4 mr-2" />
              {isGeneratingLink ? 'Generating...' : 'Generate Shareable Link'}
            </Button>

            {/* Show shareable link if generated */}
            {shareableLink && (
              <div className="p-3 bg-background-surface rounded-lg">
                <p className="text-xs text-text-muted mb-2">Shareable Link:</p>
                <div className="flex items-center gap-2">
                  <input
                    type="text"
                    value={shareableLink}
                    readOnly
                    className="flex-1 px-2 py-1 bg-background-primary border border-border rounded text-xs font-mono"
                  />
                  <Button
                    onClick={() => {
                      copyToClipboard(shareableLink);
                      toast.success('Link copied');
                    }}
                    variant="secondary"
                    size="sm"
                  >
                    <Copy className="w-3 h-3" />
                  </Button>
                </div>
              </div>
            )}

            {/* Email */}
            <Button onClick={handleShareViaEmail} variant="secondary" className="w-full">
              <Mail className="w-4 h-4 mr-2" />
              Share via Email
            </Button>

            {/* Web Share API */}
            {'share' in navigator && (
              <Button onClick={handleShareViaWebAPI} variant="secondary" className="w-full">
                <Share2 className="w-4 h-4 mr-2" />
                Share via System
              </Button>
            )}
          </div>
        </div>

        {/* Info */}
        <div className="pt-4 border-t border-border">
          <p className="text-xs text-text-muted">
            Export includes all messages, action steps, and attachments. Shared links are read-only.
          </p>
        </div>
      </div>
    </Modal>
  );
}
