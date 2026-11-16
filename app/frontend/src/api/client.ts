// Thin fetch wrapper for the StoryCore backend. Every request goes to /api/... with the X-Story-Client header the
// backend requires for state-changing calls. Errors arrive as {"detail": "...", "code": "..."}.

import { msg } from "@/i18n";

export class ApiError extends Error {
  status: number;
  code?: string;
  data: Record<string, unknown>;
  constructor(status: number, message: string, data: Record<string, unknown> = {}) {
    super(message);
    this.status = status;
    this.code = typeof data.code === "string" ? data.code : undefined;
    this.data = data;
  }
}

const CLIENT_HEADERS: Record<string, string> = { "X-Story-Client": "1" };

async function readResponse<T>(res: Response): Promise<T> {
  const text = await res.text();
  let body: unknown = null;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    body = { detail: text };
  }
  if (!res.ok) {
    const data = (body ?? {}) as Record<string, unknown>;
    // v1.8 phone access: the computer disconnected this phone (or restarted): back to the pairing page
    if (res.status === 401 && data.code === "not_paired") window.location.assign("/pair");
    let message = typeof data.detail === "string" ? data.detail : `Request failed (${res.status})`;
    if (Array.isArray(data.detail)) message = data.detail.map((d: { msg?: string }) => d.msg).join("; ");
    throw new ApiError(res.status, message, data);
  }
  return body as T;
}

type RequestOptions = Omit<RequestInit, "body"> & { json?: unknown; body?: BodyInit | null };

export async function request<T = unknown>(path: string, options: RequestOptions = {}): Promise<T> {
  const { json, headers, ...rest } = options;
  const h: Record<string, string> = { ...CLIENT_HEADERS, ...(headers as Record<string, string>) };
  if (json !== undefined) h["Content-Type"] = "application/json";
  let res: Response;
  try {
    res = await fetch(`/api${path}`, { ...rest, headers: h, body: json === undefined ? rest.body : JSON.stringify(json) });
  } catch {
    throw new ApiError(0, "Cannot reach the StoryCore server. Is the app still running?");
  }
  return readResponse<T>(res);
}

export const api = {
  get: <T = unknown>(path: string, signal?: AbortSignal) => request<T>(path, { signal }),
  post: <T = unknown>(path: string, json?: unknown) => request<T>(path, { method: "POST", json: json ?? {} }),
  put: <T = unknown>(path: string, json?: unknown) => request<T>(path, { method: "PUT", json: json ?? {} }),
  patch: <T = unknown>(path: string, json?: unknown) => request<T>(path, { method: "PATCH", json: json ?? {} }),
  del: <T = unknown>(path: string) => request<T>(path, { method: "DELETE" }),
  /** multipart upload (FormData); the browser sets the boundary */
  upload: async <T = unknown>(path: string, form: FormData) =>
    readResponse<T>(await fetch(`/api${path}`, { method: "POST", headers: CLIENT_HEADERS, body: form })),
};

export type StreamEvent = { event: string; data: unknown };

/** Server-sent events over fetch (so the request can be aborted and errors read). Calls onEvent for each event. */
export async function readStream(path: string, onEvent: (e: StreamEvent) => void, signal?: AbortSignal): Promise<void> {
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
      let event = "message";
      const data: string[] = [];
      for (const line of block.split("\n")) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) data.push(line.slice(5).replace(/^ /, ""));
      }
      if (!data.length) continue;
      const raw = data.join("\n");
      let parsed: unknown = raw;
      try {
        parsed = JSON.parse(raw);
      } catch {
        /* plain text event */
      }
      onEvent({ event, data: parsed });
    }
  }
}

export function assetUrl(assetId: string, variant: "thumb" | "card" | "full" = "card", version?: string | number) {
  return `/api/assets/${assetId}/image?variant=${variant}${version ? `&v=${version}` : ""}`;
}

export function errorMessage(e: unknown): string {
  if (e instanceof ApiError && e.code === "pc_only") return msg("This is only available on the computer.");
  if (e instanceof ApiError) return e.message;
  if (e instanceof Error) return e.message;
  return String(e);
}
