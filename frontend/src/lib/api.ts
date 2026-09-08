export const apiBase = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api/v1";
const normalizedBase = apiBase.replace(/\/$/, "");
const healthUrl = apiBase.replace(/\/api\/v1\/?$/, "/health/live");

export type BackendStatus = "checking" | "online" | "offline";
export type JobState = "QUEUED" | "EXTRACTING" | "TRANSCRIBING" | "CHUNKING" | "INDEXING" | "READY" | "FAILED";

export interface ApiVideo {
  video_id: string;
  original_name: string;
  mime: string;
  size_bytes: number;
  duration_ms: number | null;
  created_at: string;
  state: JobState;
  progress: number;
  error_code: string | null;
}

export interface ApiTranscriptSegment {
  seq: number;
  start_ms: number;
  end_ms: number;
  text: string;
  language: string;
}

export interface ApiEvidence {
  chunk_id: string;
  video_id: string;
  start_ms: number;
  end_ms: number;
  timestamp: string;
  text: string;
}

export interface ApiSummary {
  video_id: string;
  summary: string;
  evidence: ApiEvidence[];
  cached: boolean;
  generated_at: string;
}

export interface ApiSearchResult {
  video_id: string;
  original_name: string;
  chunk_id: string;
  start_ms: number;
  end_ms: number;
  text: string;
  score: number;
}

export interface ApiAnswer {
  conversation_id: string;
  message_id: string;
  answer: string;
  refused: boolean;
  evidence: ApiEvidence[];
  created_at: string;
}

export interface ApiConversation {
  conversation_id: string;
  video_id: string;
  created_at: string;
  messages: Array<{
    message_id: string;
    role: "user" | "assistant";
    content: string;
    evidence: ApiEvidence[];
    created_at: string;
  }>;
}

export function getConversation(id: string, signal?: AbortSignal): Promise<ApiConversation> {
  return requestJson(`/conversations/${id}`, { signal });
}

interface ApiErrorBody {
  error_code?: string;
  message?: string;
  retryable?: boolean;
  request_id?: string;
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly errorCode = "REQUEST_FAILED",
    readonly retryable = false,
    readonly requestId?: string,
  ) {
    super(message);
  }
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${normalizedBase}${path}`, init);
  } catch {
    throw new ApiError("无法连接后端服务，请检查服务是否已启动。", 0, "NETWORK_ERROR", true);
  }
  if (!response.ok) {
    let body: ApiErrorBody = {};
    try {
      body = await response.json() as ApiErrorBody;
    } catch {
      // The status code remains useful when a proxy returns a non-JSON error page.
    }
    throw new ApiError(
      body.message || `请求失败（HTTP ${response.status}）。`,
      response.status,
      body.error_code,
      body.retryable,
      body.request_id,
    );
  }
  return response.json() as Promise<T>;
}

export async function checkBackend(): Promise<BackendStatus> {
  try {
    const response = await fetch(healthUrl);
    return response.ok ? "online" : "offline";
  } catch {
    return "offline";
  }
}

export function videoContentUrl(videoId: string) {
  return `${normalizedBase}/videos/${videoId}/content`;
}

export async function listVideos(signal?: AbortSignal): Promise<ApiVideo[]> {
  const response = await requestJson<{ items: ApiVideo[] }>("/videos", { signal });
  return response.items;
}

export function getVideo(videoId: string, signal?: AbortSignal): Promise<ApiVideo> {
  return requestJson(`/videos/${videoId}`, { signal });
}

export async function getTranscript(videoId: string, signal?: AbortSignal): Promise<ApiTranscriptSegment[]> {
  const response = await requestJson<{ segments: ApiTranscriptSegment[] }>(`/videos/${videoId}/transcript`, { signal });
  return response.segments;
}

export async function uploadVideo(file: File, signal?: AbortSignal): Promise<{ video_id: string; state: JobState }> {
  const formData = new FormData();
  formData.append("file", file);
  return requestJson("/videos", { method: "POST", body: formData, signal });
}

export async function searchVideos(query: string, videoIds: string[], signal?: AbortSignal): Promise<ApiSearchResult[]> {
  const response = await requestJson<{ results: ApiSearchResult[] }>("/search", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, video_ids: videoIds, limit: 20 }),
    signal,
  });
  return response.results;
}

export function getSummary(videoId: string, signal?: AbortSignal): Promise<ApiSummary> {
  return requestJson(`/videos/${videoId}/summary`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ language: "auto", length: "medium", format: "outline" }),
    signal,
  });
}

export async function createConversation(videoId: string): Promise<string> {
  const response = await requestJson<{ conversation_id: string }>("/conversations", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ video_id: videoId }),
  });
  return response.conversation_id;
}

export function askQuestion(conversationId: string, question: string): Promise<ApiAnswer> {
  return requestJson(`/conversations/${conversationId}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
  });
}
