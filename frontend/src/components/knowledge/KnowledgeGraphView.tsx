import React, { useCallback, useMemo, useState, useEffect, useRef } from 'react';
import ReactFlow, {
  type Node,
  type Edge,
  type Connection,
  Controls,
  Background,
  ConnectionMode,
  useNodesState,
  useEdgesState,
  MiniMap,
} from 'reactflow';
import 'reactflow/dist/style.css';
import { useKnowledgeGraphStore, type KnowledgeNode, type NodeType } from '../../stores';
import { EmptyState } from '../ui/EmptyState';
import { Brain, FileText, MessageCircle, Database, Plus, Search, Download, Upload, Filter, X } from 'lucide-react';
import { NodeDetailPanel } from './NodeDetailPanel';
import { NodeEditorModal } from './NodeEditorModal';
import { EdgeEditorModal } from './EdgeEditorModal';
import { computeForceLayout } from '../../utils/graphLayout';
import {
  exportGraphAsJSON,
  exportGraphAsGraphML,
  importGraphFromJSON,
  downloadFile,
} from '../../utils/graphExport';

const nodeTypeIcons = {
  concept: Brain,
  entity: Database,
  memory: Database,
  conversation: MessageCircle,
  file: FileText,
};

const nodeTypeColors: Record<string, string> = {
  concept: '#8B5CF6',
  entity: '#3B82F6',
  memory: '#10B981',
  conversation: '#F59E0B',
  file: '#EC4899',
};

const allNodeTypes: { value: NodeType; label: string }[] = [
  { value: 'concept', label: 'Concept' },
  { value: 'entity', label: 'Entity' },
  { value: 'memory', label: 'Memory' },
  { value: 'conversation', label: 'Conversation' },
  { value: 'file', label: 'File' },
];

export function KnowledgeGraphView() {
  const {
    nodes: knowledgeNodes,
    edges: knowledgeEdges,
    addNode,
    updateNode,
    removeNode,
    addEdge: addKnowledgeEdge,
    importGraph,
    exportGraph,
    searchNodes,
  } = useKnowledgeGraphStore();

  const [selectedNode, setSelectedNode] = useState<KnowledgeNode | null>(null);
  const [showNodeEditor, setShowNodeEditor] = useState(false);
  const [editingNode, setEditingNode] = useState<KnowledgeNode | null>(null);
  const [showEdgeEditor, setShowEdgeEditor] = useState(false);
  const [pendingConnection, setPendingConnection] = useState<{ source: string; target: string } | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [filterType, setFilterType] = useState<NodeType | null>(null);
  const [showFilters, setShowFilters] = useState(false);
  const [showExportMenu, setShowExportMenu] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Filter nodes based on search and type filter
  const filteredNodes = useMemo(() => {
    let result = knowledgeNodes;
    if (searchQuery) {
      result = searchNodes(searchQuery);
    }
    if (filterType) {
      result = result.filter((n) => n.type === filterType);
    }
    return result;
  }, [knowledgeNodes, searchQuery, filterType, searchNodes]);

  const filteredNodeIds = useMemo(() => new Set(filteredNodes.map((n) => n.id)), [filteredNodes]);

  const filteredEdges = useMemo(() => {
    return knowledgeEdges.filter(
      (e) => filteredNodeIds.has(e.source) && filteredNodeIds.has(e.target)
    );
  }, [knowledgeEdges, filteredNodeIds]);

  // Compute layout positions
  const layoutPositions = useMemo(() => {
    return computeForceLayout(filteredNodes, filteredEdges, 1000, 700);
  }, [filteredNodes, filteredEdges]);

  // Convert to React Flow nodes
  const initialNodes: Node[] = useMemo(() => {
    return filteredNodes.map((node) => {
      const pos = layoutPositions.get(node.id) || { x: 0, y: 0 };
      return {
        id: node.id,
        type: 'default',
        position: pos,
        data: {
          label: (
            <div className="flex items-center gap-2">
              {React.createElement(nodeTypeIcons[node.type], {
                className: 'w-4 h-4',
                style: { color: nodeTypeColors[node.type] },
              })}
              <span className="font-medium text-sm">{node.label}</span>
            </div>
          ),
          node,
        },
        style: {
          border: `2px solid ${nodeTypeColors[node.type]}`,
          borderRadius: '8px',
          padding: '8px 12px',
          background: 'white',
          boxShadow: selectedNode?.id === node.id ? `0 0 0 3px ${nodeTypeColors[node.type]}40` : undefined,
        },
      };
    });
  }, [filteredNodes, layoutPositions, selectedNode]);

  // Convert to React Flow edges
  const initialEdges: Edge[] = useMemo(() => {
    return filteredEdges.map((edge) => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      label: edge.label || edge.type,
      type: 'default',
      animated: true,
      style: { stroke: '#94A3B8', strokeWidth: 2 },
      labelStyle: { fontSize: 11, fill: '#64748B' },
    }));
  }, [filteredEdges]);

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

  // Sync when data changes
  useEffect(() => {
    setNodes(initialNodes);
  }, [initialNodes, setNodes]);

  useEffect(() => {
    setEdges(initialEdges);
  }, [initialEdges, setEdges]);

  const onNodeClick = useCallback((_event: React.MouseEvent, node: Node) => {
    setSelectedNode(node.data.node);
  }, []);

  const onConnect = useCallback(
    (params: Connection) => {
      if (params.source && params.target) {
        setPendingConnection({ source: params.source, target: params.target });
        setShowEdgeEditor(true);
      }
    },
    []
  );

  const handleSaveNode = (node: KnowledgeNode) => {
    const existing = knowledgeNodes.find((n) => n.id === node.id);
    if (existing) {
      updateNode(node.id, node);
    } else {
      addNode(node);
    }
    setShowNodeEditor(false);
    setEditingNode(null);
  };

  const handleSaveEdge = (edge: typeof knowledgeEdges[number]) => {
    addKnowledgeEdge(edge);
    setShowEdgeEditor(false);
    setPendingConnection(null);
  };

  const handleEditNode = () => {
    if (selectedNode) {
      setEditingNode(selectedNode);
      setShowNodeEditor(true);
    }
  };

  const handleDeleteNode = () => {
    if (selectedNode) {
      removeNode(selectedNode.id);
      setSelectedNode(null);
    }
  };

  const handleExportJSON = () => {
    const data = exportGraph();
    const json = exportGraphAsJSON(data.nodes, data.edges);
    downloadFile(json, `knowledge-graph-${new Date().toISOString().split('T')[0]}.json`, 'application/json');
    setShowExportMenu(false);
  };

  const handleExportGraphML = () => {
    const data = exportGraph();
    const graphml = exportGraphAsGraphML(data.nodes, data.edges);
    downloadFile(graphml, `knowledge-graph-${new Date().toISOString().split('T')[0]}.graphml`, 'application/xml');
    setShowExportMenu(false);
  };

  const handleImport = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (e) => {
      try {
        const content = e.target?.result as string;
        const { nodes: importedNodes, edges: importedEdges } = importGraphFromJSON(content);
        importGraph(importedNodes, importedEdges);
      } catch (err) {
        alert('Failed to import graph: ' + (err instanceof Error ? err.message : 'Unknown error'));
      }
    };
    reader.readAsText(file);
    event.target.value = '';
    setShowExportMenu(false);
  };

  const sourceNode = pendingConnection
    ? knowledgeNodes.find((n) => n.id === pendingConnection.source)
    : null;
  const targetNode = pendingConnection
    ? knowledgeNodes.find((n) => n.id === pendingConnection.target)
    : null;

  return (
    <div className="h-full w-full flex">
      <div className="flex-1 flex flex-col min-w-0">
        {/* Toolbar */}
        <div className="flex-shrink-0 flex items-center gap-3 mb-4">
          {/* Search */}
          <div className="relative flex-1 max-w-xs">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search nodes..."
              className="w-full pl-9 pr-4 py-2 bg-background-surface border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-accent-primary text-sm text-text-primary"
            />
            {searchQuery && (
              <button
                onClick={() => setSearchQuery('')}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-text-muted hover:text-text-primary"
              >
                <X className="w-4 h-4" />
              </button>
            )}
          </div>

          {/* Filter */}
          <div className="relative">
            <button
              onClick={() => setShowFilters(!showFilters)}
              className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                filterType
                  ? 'bg-accent-primary text-white'
                  : 'bg-background-surface text-text-secondary hover:bg-background-surface/80'
              }`}
            >
              <Filter className="w-4 h-4" />
              <span>{filterType || 'Filter'}</span>
            </button>
            {showFilters && (
              <div className="absolute top-full mt-1 right-0 bg-background-primary border border-border rounded-lg shadow-lg z-30 min-w-[160px]">
                <button
                  onClick={() => { setFilterType(null); setShowFilters(false); }}
                  className={`w-full text-left px-3 py-2 text-sm hover:bg-background-surface ${
                    !filterType ? 'text-accent-primary font-medium' : 'text-text-secondary'
                  }`}
                >
                  All Types
                </button>
                {allNodeTypes.map((nt) => (
                  <button
                    key={nt.value}
                    onClick={() => { setFilterType(nt.value); setShowFilters(false); }}
                    className={`w-full text-left px-3 py-2 text-sm hover:bg-background-surface ${
                      filterType === nt.value ? 'text-accent-primary font-medium' : 'text-text-secondary'
                    }`}
                  >
                    {nt.label}
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Add Node */}
          <button
            onClick={() => { setEditingNode(null); setShowNodeEditor(true); }}
            className="flex items-center gap-2 px-3 py-2 bg-accent-primary text-white rounded-lg text-sm font-medium hover:bg-accent-primary/90 transition-colors"
          >
            <Plus className="w-4 h-4" />
            <span>Add Node</span>
          </button>

          {/* Export/Import */}
          <div className="relative">
            <button
              onClick={() => setShowExportMenu(!showExportMenu)}
              className="flex items-center gap-2 px-3 py-2 bg-background-surface text-text-secondary rounded-lg text-sm font-medium hover:bg-background-surface/80 transition-colors"
            >
              <Download className="w-4 h-4" />
              <span>Export</span>
            </button>
            {showExportMenu && (
              <div className="absolute top-full mt-1 right-0 bg-background-primary border border-border rounded-lg shadow-lg z-30 min-w-[180px]">
                <button
                  onClick={handleExportJSON}
                  className="w-full text-left px-3 py-2 text-sm text-text-secondary hover:bg-background-surface flex items-center gap-2"
                >
                  <Download className="w-4 h-4" />
                  Export as JSON
                </button>
                <button
                  onClick={handleExportGraphML}
                  className="w-full text-left px-3 py-2 text-sm text-text-secondary hover:bg-background-surface flex items-center gap-2"
                >
                  <Download className="w-4 h-4" />
                  Export as GraphML
                </button>
                <button
                  onClick={() => fileInputRef.current?.click()}
                  className="w-full text-left px-3 py-2 text-sm text-text-secondary hover:bg-background-surface flex items-center gap-2"
                >
                  <Upload className="w-4 h-4" />
                  Import JSON
                </button>
              </div>
            )}
            <input
              ref={fileInputRef}
              type="file"
              accept=".json"
              onChange={handleImport}
              className="hidden"
            />
          </div>
        </div>

        {/* Graph */}
        <div className="flex-1 border border-border rounded-lg overflow-hidden">
          {filteredNodes.length === 0 ? (
            <EmptyState
              icon={<Brain className="w-16 h-16" />}
              title={searchQuery || filterType ? 'No Matching Nodes' : 'No Knowledge Yet'}
              description={
                searchQuery || filterType
                  ? 'Try adjusting your search or filter criteria.'
                  : 'Start building your knowledge graph by adding nodes.'
              }
              action={
                !searchQuery && !filterType ? (
                  <button
                    onClick={() => { setEditingNode(null); setShowNodeEditor(true); }}
                    className="inline-flex items-center gap-2 px-4 py-2 bg-accent-primary text-white rounded-lg font-medium hover:bg-accent-primary/90 transition-colors"
                  >
                    <Plus className="w-4 h-4" />
                    Add First Node
                  </button>
                ) : undefined
              }
            />
          ) : (
            <ReactFlow
              nodes={nodes}
              edges={edges}
              onNodesChange={onNodesChange}
              onEdgesChange={onEdgesChange}
              onNodeClick={onNodeClick}
              onConnect={onConnect}
              connectionMode={ConnectionMode.Loose}
              fitView
              fitViewOptions={{ padding: 0.2 }}
            >
              <Background />
              <Controls />
              <MiniMap
                nodeColor={(node) => {
                  const type = (node.data?.node as KnowledgeNode | undefined)?.type;
                  return type ? nodeTypeColors[type] : '#94A3B8';
                }}
                maskColor="rgba(0,0,0,0.1)"
              />
            </ReactFlow>
          )}
        </div>

        {/* Selection info bar */}
        {selectedNode && !showNodeEditor && (
          <div className="flex-shrink-0 mt-2 flex items-center justify-between bg-background-surface rounded-lg px-4 py-2">
            <div className="flex items-center gap-2 text-sm">
              <span
                className="w-3 h-3 rounded-full"
                style={{ backgroundColor: nodeTypeColors[selectedNode.type] }}
              />
              <span className="font-medium text-text-primary">{selectedNode.label}</span>
              <span className="text-text-muted">({selectedNode.type})</span>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={handleEditNode}
                className="text-sm text-accent-primary hover:underline"
              >
                Edit
              </button>
              <button
                onClick={handleDeleteNode}
                className="text-sm text-accent-error hover:underline"
              >
                Delete
              </button>
              <button
                onClick={() => setSelectedNode(null)}
                className="text-sm text-text-muted hover:text-text-primary"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Detail Panel */}
      {selectedNode && (
        <NodeDetailPanel
          node={selectedNode}
          edges={knowledgeEdges}
          allNodes={knowledgeNodes}
          onClose={() => setSelectedNode(null)}
          onEdit={handleEditNode}
        />
      )}

      {/* Node Editor Modal */}
      {showNodeEditor && (
        <NodeEditorModal
          node={editingNode}
          onSave={handleSaveNode}
          onClose={() => { setShowNodeEditor(false); setEditingNode(null); }}
        />
      )}

      {/* Edge Editor Modal */}
      {showEdgeEditor && pendingConnection && sourceNode && targetNode && (
        <EdgeEditorModal
          sourceNodeId={pendingConnection.source}
          targetNodeId={pendingConnection.target}
          sourceLabel={sourceNode.label}
          targetLabel={targetNode.label}
          onSave={handleSaveEdge}
          onClose={() => { setShowEdgeEditor(false); setPendingConnection(null); }}
        />
      )}
    </div>
  );
}
