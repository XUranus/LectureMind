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
  timeSecond: number; // camelCase
  imageUrl: string;
}

// Define TypeScript interfaces for type safety
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

// Define TypeScript interfaces for type safety
export interface Section {
  id: number;
  begin_time: number; // in seconds
  text: string;
}