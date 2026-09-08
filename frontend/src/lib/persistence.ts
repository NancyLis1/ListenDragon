import { apiBase } from "./api";

export function readSaved(key: string): string | undefined {
  try { return localStorage.getItem(`listen-dragon:${apiBase}:${key}`) || undefined; }
  catch { return undefined; }
}

export function saveLocal(key: string, value: string) {
  try { localStorage.setItem(`listen-dragon:${apiBase}:${key}`, value); }
  catch { /* Backend persistence still works when browser storage is unavailable. */ }
}
