import { logger } from './logger';
import type { Conversation } from '../types';

/**
 * Convert conversation to Markdown format
 */
export function conversationToMarkdown(conversation: Conversation): string {
  const lines: string[] = [];
  
  // Header
  lines.push(`# ${conversation.title}`);
  lines.push('');
  lines.push(`*Created: ${new Date(conversation.createdAt).toLocaleString()}*`);
  lines.push(`*Updated: ${new Date(conversation.updatedAt).toLocaleString()}*`);
  if (conversation.projectId) {
    lines.push(`*Project: ${conversation.projectId}*`);
  }
  lines.push('');
  lines.push('---');
  lines.push('');
  
  // Messages
  for (const message of conversation.messages) {
    const role = message.role === 'user' ? '**You**' : '**Arena**';
    const time = new Date(message.timestamp).toLocaleString();
    
    lines.push(`### ${role} — ${time}`);
    lines.push('');
    lines.push(message.content);
    lines.push('');
    
    // Action steps
    if (message.actionSteps && message.actionSteps.length > 0) {
      lines.push('**Action Steps:**');
      lines.push('');
      for (const step of message.actionSteps) {
        const status = step.status === 'complete' ? '✅' : step.status === 'error' ? '❌' : '⏳';
        lines.push(`- ${status} ${step.description}`);
        if (step.details) {
          lines.push(`  - ${step.details}`);
        }
      }
      lines.push('');
    }
    
    // Attachments
    if (message.attachments && message.attachments.length > 0) {
      lines.push('**Attachments:**');
      lines.push('');
      for (const attachment of message.attachments) {
        lines.push(`- 📎 ${attachment.name} (${attachment.type})`);
        if (attachment.analysis) {
          lines.push(`  - Analysis: ${attachment.analysis.content.substring(0, 100)}...`);
        }
      }
      lines.push('');
    }
    
    lines.push('---');
    lines.push('');
  }
  
  return lines.join('\n');
}

/**
 * Convert conversation to plain text format
 */
export function conversationToText(conversation: Conversation): string {
  const lines: string[] = [];
  
  // Header
  lines.push(conversation.title);
  lines.push('='.repeat(conversation.title.length));
  lines.push('');
  lines.push(`Created: ${new Date(conversation.createdAt).toLocaleString()}`);
  lines.push(`Updated: ${new Date(conversation.updatedAt).toLocaleString()}`);
  if (conversation.projectId) {
    lines.push(`Project: ${conversation.projectId}`);
  }
  lines.push('');
  lines.push('-'.repeat(80));
  lines.push('');
  
  // Messages
  for (const message of conversation.messages) {
    const role = message.role === 'user' ? 'YOU' : 'ARENA';
    const time = new Date(message.timestamp).toLocaleString();
    
    lines.push(`[${role}] ${time}`);
    lines.push(message.content);
    lines.push('');
    
    // Action steps
    if (message.actionSteps && message.actionSteps.length > 0) {
      lines.push('Action Steps:');
      for (const step of message.actionSteps) {
        const status = step.status === 'complete' ? '[DONE]' : step.status === 'error' ? '[ERROR]' : '[PENDING]';
        lines.push(`  ${status} ${step.description}`);
        if (step.details) {
          lines.push(`         ${step.details}`);
        }
      }
      lines.push('');
    }
    
    // Attachments
    if (message.attachments && message.attachments.length > 0) {
      lines.push('Attachments:');
      for (const attachment of message.attachments) {
        lines.push(`  - ${attachment.name} (${attachment.type})`);
      }
      lines.push('');
    }
    
    lines.push('-'.repeat(80));
    lines.push('');
  }
  
  return lines.join('\n');
}

/**
 * Convert conversation to HTML format
 */
export function conversationToHTML(conversation: Conversation): string {
  const messagesHTML = conversation.messages.map((message) => {
    const role = message.role === 'user' ? 'You' : 'Arena';
    const time = new Date(message.timestamp).toLocaleString();
    const roleClass = message.role === 'user' ? 'user' : 'assistant';
    
    let actionStepsHTML = '';
    if (message.actionSteps && message.actionSteps.length > 0) {
      const steps = message.actionSteps.map((step) => {
        const statusIcon = step.status === 'complete' ? '✅' : step.status === 'error' ? '❌' : '⏳';
        return `<li>${statusIcon} ${step.description}${step.details ? `<br><small>${step.details}</small>` : ''}</li>`;
      }).join('');
      actionStepsHTML = `<div class="action-steps"><strong>Action Steps:</strong><ul>${steps}</ul></div>`;
    }
    
    let attachmentsHTML = '';
    if (message.attachments && message.attachments.length > 0) {
      const attachments = message.attachments.map((attachment) => {
        return `<li>📎 ${attachment.name} (${attachment.type})</li>`;
      }).join('');
      attachmentsHTML = `<div class="attachments"><strong>Attachments:</strong><ul>${attachments}</ul></div>`;
    }
    
    return `
      <div class="message ${roleClass}">
        <div class="message-header">
          <strong>${role}</strong> — <small>${time}</small>
        </div>
        <div class="message-content">${message.content.replace(/\n/g, '<br>')}</div>
        ${actionStepsHTML}
        ${attachmentsHTML}
      </div>
    `;
  }).join('');
  
  return `
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>${conversation.title}</title>
  <style>
    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
      max-width: 800px;
      margin: 0 auto;
      padding: 20px;
      background: #f5f5f5;
      color: #333;
    }
    .header {
      background: white;
      padding: 20px;
      border-radius: 8px;
      margin-bottom: 20px;
      box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    .header h1 {
      margin: 0 0 10px 0;
      color: #1a1a1a;
    }
    .header .meta {
      color: #666;
      font-size: 14px;
    }
    .message {
      background: white;
      padding: 15px;
      border-radius: 8px;
      margin-bottom: 15px;
      box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    .message.user {
      border-left: 4px solid #3b82f6;
    }
    .message.assistant {
      border-left: 4px solid #8b5cf6;
    }
    .message-header {
      margin-bottom: 10px;
      color: #666;
      font-size: 14px;
    }
    .message-content {
      line-height: 1.6;
    }
    .action-steps, .attachments {
      margin-top: 15px;
      padding-top: 15px;
      border-top: 1px solid #e5e5e5;
    }
    .action-steps ul, .attachments ul {
      margin: 10px 0 0 0;
      padding-left: 20px;
    }
    .action-steps li, .attachments li {
      margin-bottom: 5px;
    }
  </style>
</head>
<body>
  <div class="header">
    <h1>${conversation.title}</h1>
    <div class="meta">
      <p>Created: ${new Date(conversation.createdAt).toLocaleString()}</p>
      <p>Updated: ${new Date(conversation.updatedAt).toLocaleString()}</p>
      ${conversation.projectId ? `<p>Project: ${conversation.projectId}</p>` : ''}
    </div>
  </div>
  ${messagesHTML}
</body>
</html>
  `.trim();
}

/**
 * Download content as a file
 */
export function downloadFile(content: string, filename: string, mimeType: string): void {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

/**
 * Copy content to clipboard
 */
export async function copyToClipboard(content: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(content);
    return true;
  } catch (error) {
    logger.error('Failed to copy to clipboard:', error);
    return false;
  }
}

/**
 * Generate shareable link (placeholder - would integrate with backend)
 */
export async function generateShareableLink(conversationId: string): Promise<string> {
  // In production, this would call the backend to generate a shareable link
  // For now, return a placeholder
  return `${window.location.origin}/shared/${conversationId}`;
}

/**
 * Share via email
 */
export function shareViaEmail(conversation: Conversation): void {
  const subject = encodeURIComponent(`Arena Conversation: ${conversation.title}`);
  const body = encodeURIComponent(conversationToText(conversation));
  const mailtoLink = `mailto:?subject=${subject}&body=${body}`;
  window.location.href = mailtoLink;
}

/**
 * Share via Web Share API (if available)
 */
export async function shareViaWebAPI(conversation: Conversation): Promise<boolean> {
  if (!navigator.share) {
    return false;
  }
  
  try {
    await navigator.share({
      title: conversation.title,
      text: conversationToText(conversation).substring(0, 500) + '...',
      url: window.location.href,
    });
    return true;
  } catch (error) {
    logger.error('Failed to share via Web Share API:', error);
    return false;
  }
}
