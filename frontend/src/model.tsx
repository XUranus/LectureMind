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

export interface SectionWithKnowledge extends Section {
  knowledge_points: KnowledgePoint[];
}

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

export interface MindmapTreeNode {
  id: string;
  label: string;
  children: MindmapTreeNode[];
}

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

export interface KnowledgeMindmapData {
  video: string;
  tree_data: MindmapTreeNode;
  react_flow_nodes: ReactFlowNodeData[];
  react_flow_edges: ReactFlowEdgeData[];
  created_at: string;
  updated_at: string;
}

// Chat — RAG chatbot types

export interface Citation {
  source_num: number;
  title: string;
  begin_time: number;
  end_time: number;
  type: string;
  relevance: number;
}

export interface ChatMessageData {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  citations: Citation[];
  toolSteps?: AgentToolStep[];
  created_at?: string;
}

export interface ChatSessionData {
  id: string;
  video: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
}

// Agent — LangGraph tool orchestration types

export interface AgentToolStep {
  tool: string;
  args: Record<string, any>;
  result?: string;
}

export type AgentEventType =
  | 'thinking'
  | 'tool_call'
  | 'tool_result'
  | 'token'
  | 'citations'
  | 'done'
  | 'complete'
  | 'error';

export interface AgentEvent {
  event: AgentEventType;
  data: Record<string, any>;
}
