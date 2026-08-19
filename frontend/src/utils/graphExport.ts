import type { KnowledgeNode, KnowledgeEdge } from '../stores/knowledgeGraphStore';
import type { Memory } from '../stores/memoryBrowserStore';
import type { Conversation } from '../types';

export function exportGraphAsJSON(nodes: KnowledgeNode[], edges: KnowledgeEdge[]): string {
  return JSON.stringify({ nodes, edges }, null, 2);
}

export function exportGraphAsGraphML(nodes: KnowledgeNode[], edges: KnowledgeEdge[]): string {
  const nodeEntries = nodes.map((node) => {
    const data = [
      `<data key="type">${escapeXml(node.type)}</data>`,
      `<data key="label">${escapeXml(node.label)}</data>`,
      node.description ? `<data key="description">${escapeXml(node.description)}</data>` : '',
      `<data key="importance">${node.metadata.importance}</data>`,
      `<data key="tags">${escapeXml(node.metadata.tags.join(','))}</data>`,
      `<data key="createdAt">${escapeXml(node.metadata.createdAt)}</data>`,
    ].filter(Boolean).join('\n      ');

    return `    <node id="${escapeXml(node.id)}">
      ${data}
    </node>`;
  }).join('\n');

  const edgeEntries = edges.map((edge) => {
    const data = [
      `<data key="edgeType">${escapeXml(edge.type)}</data>`,
      edge.label ? `<data key="edgeLabel">${escapeXml(edge.label)}</data>` : '',
      `<data key="weight">${edge.metadata.weight}</data>`,
    ].filter(Boolean).join('\n      ');

    return `    <edge id="${escapeXml(edge.id)}" source="${escapeXml(edge.source)}" target="${escapeXml(edge.target)}">
      ${data}
    </edge>`;
  }).join('\n');

  return `<?xml version="1.0" encoding="UTF-8"?>
<graphml xmlns="http://graphml.graphdrawing.org/xmlns"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://graphml.graphdrawing.org/xmlns
         http://graphml.graphdrawing.org/xmlns/1.0/graphml.xsd">

  <key id="type" for="node" attr.name="type" attr.type="string"/>
  <key id="label" for="node" attr.name="label" attr.type="string"/>
  <key id="description" for="node" attr.name="description" attr.type="string"/>
  <key id="importance" for="node" attr.name="importance" attr.type="int"/>
  <key id="tags" for="node" attr.name="tags" attr.type="string"/>
  <key id="createdAt" for="node" attr.name="createdAt" attr.type="string"/>
  <key id="edgeType" for="edge" attr.name="type" attr.type="string"/>
  <key id="edgeLabel" for="edge" attr.name="label" attr.type="string"/>
  <key id="weight" for="edge" attr.name="weight" attr.type="int"/>

  <graph id="knowledge-graph" edgedefault="directed">
${nodeEntries}
${edgeEntries}
  </graph>
</graphml>`;
}

export function importGraphFromJSON(json: string): { nodes: KnowledgeNode[]; edges: KnowledgeEdge[] } {
  const parsed = JSON.parse(json);
  if (!Array.isArray(parsed.nodes) || !Array.isArray(parsed.edges)) {
    throw new Error('Invalid graph JSON format');
  }
  return { nodes: parsed.nodes, edges: parsed.edges };
}

export function exportMemoriesAsJSON(memories: Memory[]): string {
  return JSON.stringify(memories, null, 2);
}

export function importMemoriesFromJSON(json: string): Memory[] {
  const parsed = JSON.parse(json);
  if (!Array.isArray(parsed)) {
    throw new Error('Invalid memories JSON format');
  }
  return parsed;
}

export function exportConversationAsMarkdown(conv: Conversation): string {
  const lines: string[] = [
    `# ${conv.title}`,
    '',
    `*Created: ${new Date(conv.createdAt).toLocaleString()}*`,
    `*Updated: ${new Date(conv.updatedAt).toLocaleString()}*`,
    '',
    '---',
    '',
  ];

  for (const msg of conv.messages) {
    const role = msg.role === 'user' ? '**You**' : '**Arena**';
    const time = new Date(msg.timestamp).toLocaleString();
    lines.push(`### ${role} — ${time}`);
    lines.push('');
    lines.push(msg.content);
    lines.push('');
  }

  return lines.join('\n');
}

export function exportConversationsAsMarkdown(conversations: Conversation[]): string {
  return conversations.map(exportConversationAsMarkdown).join('\n\n---\n\n');
}

function escapeXml(str: string): string {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&apos;');
}

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
