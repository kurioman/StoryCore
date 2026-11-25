import { msg } from "@/i18n";
// Reconstructed from the StoryCore v1.7.0 compiled bundle (see DEVONLY/13_FRONTEND_SOURCE.md).
import { clsx } from "clsx";

export var cn = (...e) => clsx(e);

export function timeAgo(e) {
  if (!e) return ``;
  let t = new Date(e).getTime(),
    n = Math.round((Date.now() - t) / 1e3);
  return n < 45
    ? msg("just now")
    : n < 3600
      ? msg("{{v0}} min ago", { v0: Math.round(n / 60) })
      : n < 86400
        ? msg("{{v0}} h ago", { v0: Math.round(n / 3600) })
        : n < 604800
          ? msg("{{v0}} d ago", { v0: Math.round(n / 86400) })
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
  saveBlob(e, new Blob([JSON.stringify(t, null, 2)], { type: `application/json` }));
}

// Saves a file made by the interface. In the Android app (mobile/android) a WebView cannot download a blob: the
// file goes to the app through its bridge (window.StoryCoreAndroid), which asks the player where to save it.
export function saveBlob(name, blob) {
  let bridge = typeof window !== `undefined` ? window.StoryCoreAndroid : undefined;
  if (bridge?.saveFile) {
    let reader = new FileReader();
    reader.onload = () => bridge.saveFile(name, blob.type || `application/octet-stream`, String(reader.result).split(`,`)[1] ?? ``);
    reader.readAsDataURL(blob);
    return;
  }
  let url = URL.createObjectURL(blob),
    link = document.createElement(`a`);
  link.href = url;
  link.download = name;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}

export function readFileText(e) {
  return new Promise((t, n) => {
    let r = new FileReader();
    ((r.onload = () => t(String(r.result))), (r.onerror = () => n(r.error)), r.readAsText(e));
  });
}
