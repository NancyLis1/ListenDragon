export type AppView = "upload" | "search" | "reader";

export type ProcessingState = "complete" | "working" | "pending";

export interface ProcessingStep {
  id: string;
  title: string;
  description: string;
  state: ProcessingState;
  detail: string;
}

export interface Lecture {
  id: string;
  title: string;
  source: string;
  year: string;
  duration: string;
  timeRange: string;
  timestamp: string;
  preview: string;
  visual: "rope" | "attention" | "sequence" | "science";
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  time: string;
}
