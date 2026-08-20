import type { KnowledgeNode, KnowledgeEdge } from '../stores/knowledgeGraphStore';

interface LayoutNode {
  id: string;
  x: number;
  y: number;
}

export function computeForceLayout(
  nodes: KnowledgeNode[],
  edges: KnowledgeEdge[],
  width: number = 800,
  height: number = 600,
  iterations: number = 100
): Map<string, { x: number; y: number }> {
  if (nodes.length === 0) return new Map();

  // Initialize positions in a circle
  const layoutNodes: LayoutNode[] = nodes.map((node, i) => {
    const angle = (2 * Math.PI * i) / nodes.length;
    const radius = Math.min(width, height) * 0.35;
    return {
      id: node.id,
      x: width / 2 + radius * Math.cos(angle),
      y: height / 2 + radius * Math.sin(angle),
    };
  });

  const nodeMap = new Map<string, LayoutNode>();
  layoutNodes.forEach((n) => nodeMap.set(n.id, n));

  // Build adjacency for connected components
  const adjacency = new Map<string, Set<string>>();
  nodes.forEach((n) => adjacency.set(n.id, new Set()));
  edges.forEach((e) => {
    adjacency.get(e.source)?.add(e.target);
    adjacency.get(e.target)?.add(e.source);
  });

  // Simple force-directed layout
  const k = Math.sqrt((width * height) / nodes.length);
  const idealDistance = k * 1.5;

  for (let iter = 0; iter < iterations; iter++) {
    const temperature = (1 - iter / iterations) * 50;
    const forces = new Map<string, { fx: number; fy: number }>();
    layoutNodes.forEach((n) => forces.set(n.id, { fx: 0, fy: 0 }));

    // Repulsive forces between all pairs
    for (let i = 0; i < layoutNodes.length; i++) {
      for (let j = i + 1; j < layoutNodes.length; j++) {
        const a = layoutNodes[i];
        const b = layoutNodes[j];
        const dx = a.x - b.x;
        const dy = a.y - b.y;
        const dist = Math.max(Math.sqrt(dx * dx + dy * dy), 1);
        const force = (idealDistance * idealDistance) / dist;
        const fx = (dx / dist) * force;
        const fy = (dy / dist) * force;

        const fa = forces.get(a.id)!;
        const fb = forces.get(b.id)!;
        fa.fx += fx;
        fa.fy += fy;
        fb.fx -= fx;
        fb.fy -= fy;
      }
    }

    // Attractive forces along edges
    for (const edge of edges) {
      const a = nodeMap.get(edge.source);
      const b = nodeMap.get(edge.target);
      if (!a || !b) continue;

      const dx = a.x - b.x;
      const dy = a.y - b.y;
      const dist = Math.max(Math.sqrt(dx * dx + dy * dy), 1);
      const force = (dist * dist) / idealDistance;
      const fx = (dx / dist) * force;
      const fy = (dy / dist) * force;

      const fa = forces.get(a.id)!;
      const fb = forces.get(b.id)!;
      fa.fx -= fx;
      fa.fy -= fy;
      fb.fx += fx;
      fb.fy += fy;
    }

    // Apply forces with temperature limiting
    for (const node of layoutNodes) {
      const f = forces.get(node.id)!;
      const magnitude = Math.sqrt(f.fx * f.fx + f.fy * f.fy);
      if (magnitude > 0) {
        const scale = Math.min(magnitude, temperature) / magnitude;
        node.x += f.fx * scale;
        node.y += f.fy * scale;
      }

      // Keep within bounds with padding
      const padding = 60;
      node.x = Math.max(padding, Math.min(width - padding, node.x));
      node.y = Math.max(padding, Math.min(height - padding, node.y));
    }
  }

  const result = new Map<string, { x: number; y: number }>();
  layoutNodes.forEach((n) => result.set(n.id, { x: n.x, y: n.y }));
  return result;
}
