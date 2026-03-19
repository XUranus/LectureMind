// Define TypeScript interfaces

export interface Video {
  id: string;
  cover: string;
  title: string;
  video_url: string;
  duration: number;
}

export interface Course {
  id: string;
  title: string;
  description: string;
  created_at: string;
  videos: Video[];
}

export interface ThumbnailItem {
  id: string;
  timeSecond: number;
  imageUrl: string;
}

export interface Sentence {
  channel_id: number;
  sentence_id: number;
  begin_time: number;
  end_time: number;
  language: string;
  emotion: string;
  text: string;
}

export interface TranscriptData {
  video_id: string;
  file_url: string;
  format: string;
  sample_rate: number;
  sentences: Sentence[];
}

// Video section produced by hybrid chunker
export interface Section {
  id: string;
  video: string;
  title: string;
  begin_time: number;
  end_time: number;
  transcript_text: string;
  thumbnail_url: string | null;
  order: number;
}

// Knowledge point extracted from a section by LLM
export interface KnowledgePoint {
  id: string;
  section: string;
  video: string;
  title: string;
  summary: string;
  key_terms: string[];
  importance: number;
  created_at: string;
  section_title: string;
  section_order: number;
  begin_time: number;
  end_time: number;
}

// Section with nested knowledge points
export interface SectionWithKnowledge extends Section {
  knowledge_points: KnowledgePoint[];
}

// Coarse-grained video summary
export interface KnowledgeSummaryData {
  video: string;
  overview: string;
  key_topics: string[];
  learning_objectives: string[];
  prerequisites: string[];
  difficulty_level: string;
  created_at: string;
  updated_at: string;
}

// Mindmap node (tree structure from backend)
export interface MindmapTreeNode {
  id: string;
  label: string;
  children: MindmapTreeNode[];
}

// React Flow node/edge from backend
export interface ReactFlowNodeData {
  id: string;
  type: string;
  data: { label: string };
  position: { x: number; y: number };
  style?: Record<string, any>;
}

export interface ReactFlowEdgeData {
  id: string;
  source: string;
  target: string;
  type?: string;
  animated?: boolean;
  style?: Record<string, any>;
}

// Full mindmap response
export interface KnowledgeMindmapData {
  video: string;
  tree_data: MindmapTreeNode;
  react_flow_nodes: ReactFlowNodeData[];
  react_flow_edges: ReactFlowEdgeData[];
  created_at: string;
  updated_at: string;
}
