// Reconstructed from the StoryCore v1.7.0 compiled bundle (see DEVONLY/13_FRONTEND_SOURCE.md).
import { clsx } from "clsx";

export var cn = (...e) => clsx(e);

export function timeAgo(e) {
  if (!e) return ``;
  let t = new Date(e).getTime(),
    n = Math.round((Date.now() - t) / 1e3);
  return n < 45
    ? `just now`
    : n < 3600
      ? `${Math.round(n / 60)} min ago`
      : n < 86400
        ? `${Math.round(n / 3600)} h ago`
        : n < 604800
          ? `${Math.round(n / 86400)} d ago`
          : new Date(e).toLocaleDateString();
}

export var fmtK = (e) => (e >= 1e3 ? `${(e / 1e3).toFixed(1)}k` : String(e)),
  estimateTokens = (e) => Math.ceil((e || ``).length / 4),
  uuid = () =>
    crypto.randomUUID ? crypto.randomUUID() : Math.random().toString(36).slice(2) + Date.now().toString(36),
  shortId = () => uuid().replace(/-/g, ``).slice(0, 12),
  isCloudModelId = (e) => /(?:[:-])cloud$/i.test(e);

export function fmtBytes(e) {
  if (e == null) return `unknown size`;
  let t = [`B`, `KB`, `MB`, `GB`, `TB`],
    n = 0,
    r = e;
  for (; r >= 1024 && n < t.length - 1;) ((r /= 1024), n++);
  return `${r.toFixed(r >= 10 || n === 0 ? 0 : 1)} ${t[n]}`;
}

export function downloadJson(e, t) {
  let n = new Blob([JSON.stringify(t, null, 2)], {
      type: `application/json`,
    }),
    r = document.createElement(`a`);
  ((r.href = URL.createObjectURL(n)), (r.download = e), r.click(), setTimeout(() => URL.revokeObjectURL(r.href), 1e3));
}

export function readFileText(e) {
  return new Promise((t, n) => {
    let r = new FileReader();
    ((r.onload = () => t(String(r.result))), (r.onerror = () => n(r.error)), r.readAsText(e));
  });
}
