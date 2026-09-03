export const apiBase = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api/v1";
const healthUrl = apiBase.replace(/\/api\/v1\/?$/, "/health/live");

export type BackendStatus = "checking" | "online" | "offline";

export async function checkBackend(): Promise<BackendStatus> {
  try {
    const response = await fetch(healthUrl);
    return response.ok ? "online" : "offline";
  } catch {
    return "offline";
  }
}

export interface UploadJob {
  video_id: string;
  state: string;
}

export async function uploadVideo(file: File): Promise<UploadJob> {
  const formData = new FormData();
  formData.append("file", file);
  const response = await fetch(`${apiBase.replace(/\/$/, "")}/videos`, { method: "POST", body: formData });

  if (!response.ok) {
    throw new Error("视频上传失败，请稍后重试。");
  }
  return response.json() as Promise<UploadJob>;
}
