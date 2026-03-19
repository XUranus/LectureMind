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
  begin_time: number; // in milliseconds
  end_time: number;   // in milliseconds
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
  begin_time: number;  // in seconds
  end_time: number;    // in seconds
  transcript_text: string;
  thumbnail_url: string | null;
  order: number;
}

// Knowledge point extracted from a section by LLM
export interface KnowledgePoint {
  id: string;
  section: string;       // section UUID
  video: string;         // video UUID
  title: string;
  summary: string;
  key_terms: string[];
  importance: number;    // 0.0 - 1.0
  created_at: string;
  // Denormalized section context
  section_title: string;
  section_order: number;
  begin_time: number;    // section begin time in seconds
  end_time: number;      // section end time in seconds
}

// Section with nested knowledge points (grouped API response)
export interface SectionWithKnowledge extends Section {
  knowledge_points: KnowledgePoint[];
}
