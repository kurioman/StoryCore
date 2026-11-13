// The request helpers the screens use. Same behaviour as the v1.7.0 interface: apiGet can validate the response
// with a zod schema; apiStream reads server-sent events and passes each event's parsed JSON.
import type { ZodType } from "zod";
import { ApiError, errorMessage, request } from "./client";

export { ApiError, errorMessage };

export async function apiGet<T = any>(path: string, schema?: ZodType<T>): Promise<T> {
  const data = await request<unknown>(path);
  if (!schema) return data as T;
  const parsed = schema.safeParse(data);
  if (!parsed.success) {
    console.error("Unexpected response shape", path, parsed.error);
    throw new ApiError(500, `Unexpected response from ${path}`);
  }
  return parsed.data;
}

export const apiPost = <T = any>(path: string, json?: unknown) => request<T>(path, { method: "POST", json: json ?? {} });
export const apiPut = <T = any>(path: string, json?: unknown) => request<T>(path, { method: "PUT", json: json ?? {} });
export const apiPatch = <T = any>(path: string, json?: unknown) => request<T>(path, { method: "PATCH", json: json ?? {} });
export const apiDelete = <T = any>(path: string) => request<T>(path, { method: "DELETE" });

/** multipart upload (FormData) */
export async function apiUpload<T = any>(path: string, body: FormData): Promise<T> {
  return request<T>(path, { method: "POST", body });
}

/** Server-sent events: calls onEvent with each event's JSON payload. Resolves when the stream ends. */
export async function apiStream(path: string, onEvent: (data: any) => void, signal?: AbortSignal): Promise<void> {
  const res = await fetch(`/api${path}`, { headers: { Accept: "text/event-stream" }, signal });
  if (!res.ok || !res.body) throw new ApiError(res.status, "Could not open the stream");
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let cut: number;
    while ((cut = buffer.indexOf("\n\n")) >= 0) {
      const block = buffer.slice(0, cut);
      buffer = buffer.slice(cut + 2);
      const data = block
        .split("\n")
        .filter((l) => l.startsWith("data:"))
        .map((l) => l.slice(5).trimStart())
        .join("\n");
      if (!data) continue;
      try {
        onEvent(JSON.parse(data));
      } catch {
        /* keep-alive or partial line */
      }
    }
  }
}
