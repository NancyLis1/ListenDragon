export type AppView = "upload" | "search" | "reader";

export type ProcessingState = "complete" | "working" | "pending";

export interface ProcessingStep {
  id: string;
  title: string;
  description: string;
  state: ProcessingState;
  detail: string;
}

export interface TranscriptSegment {
  id: string;
  startMs: number;
  endMs: number;
  content: string;
}

export interface DemoQaRule {
  keywords: string[];
  answer: string;
  citationMs: number;
}

export interface Lecture {
  id: string;
  title: string;
  source: string;
  year: string;
  duration: string;
  durationMs: number;
  timeRange: string;
  timestamp: string;
  timestampMs: number;
  preview: string;
  visual: "rope" | "attention" | "sequence" | "science";
}

export interface LectureDetail extends Lecture {
  transcript: TranscriptSegment[];
  qaRules: DemoQaRule[];
  videoUrl?: string;
  isDemoUpload?: boolean;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  time: string;
  citationMs?: number;
}

export interface SeekRequest {
  timeMs: number;
  token: number;
}
