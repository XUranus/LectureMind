import { useState, useEffect, useCallback } from 'react';
import { Spin, Empty } from 'antd';
import {
  ReactFlow,
  Controls,
  Background,
  MiniMap,
  useNodesState,
  useEdgesState,
  BackgroundVariant,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';

import { API_PREFIX } from '../../config';
import { KnowledgeMindmapData } from '../../model';

interface LectureMindmapProps {
  videoId?: string;
}

const LectureMindmap: React.FC<LectureMindmapProps> = ({ videoId }) => {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);

  useEffect(() => {
    const fetchMindmap = async () => {
      setLoading(true);
      setError(null);
      try {
        const response = await fetch(`${API_PREFIX}/api/videos/${videoId}/mindmap/`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data: KnowledgeMindmapData = await response.json();

        if (data.react_flow_nodes && data.react_flow_nodes.length > 0) {
          setNodes(data.react_flow_nodes as any);
          setEdges(data.react_flow_edges as any);
        } else {
          setError('No mindmap data');
        }
      } catch (err: any) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };
    if (videoId) fetchMindmap();
  }, [videoId, setNodes, setEdges]);


  if (loading) {
    return (
      <div className="flex items-center justify-center h-full min-h-[400px]">
        <Spin size="large" tip="Loading mindmap..." />
      </div>
    );
  }

  if (error || nodes.length === 0) {
    return (
      <Empty description="No mindmap available yet. Process the video to generate a mindmap." />
    );
  }

  return (
    <div style={{ width: '100%', height: '600px' }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        fitView
        fitViewOptions={{ padding: 0.3 }}
        minZoom={0.2}
        maxZoom={2}
        attributionPosition="bottom-left"
      >
        <Controls position="top-right" />
        <MiniMap
          nodeStrokeColor="#6366F1"
          nodeColor={(n) => {
            const bg = n.style?.background;
            return typeof bg === 'string' ? bg : '#E5E7EB';
          }}
          maskColor="rgba(255, 255, 255, 0.7)"
          position="bottom-right"
        />
        <Background variant={BackgroundVariant.Dots} gap={16} size={1} color="#E5E7EB" />
      </ReactFlow>
    </div>
  );
};

export default LectureMindmap;
