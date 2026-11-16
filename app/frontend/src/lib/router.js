// Reconstructed from the StoryCore v1.7.0 compiled bundle (see DEVONLY/13_FRONTEND_SOURCE.md).
import * as React from "react";
import { needsReloadOnLeave } from "@/i18n";

function subscribeHash(e) {
  return (window.addEventListener(`hashchange`, e), () => window.removeEventListener(`hashchange`, e));
}

export function useHashPath() {
  return React.useSyncExternalStore(subscribeHash, () => window.location.hash.replace(/^#/, ``) || `/`);
}

export function navigate(e) {
  if (window.location.hash.replace(/^#/, ``) === e) return;
  window.location.hash = e;
  // the language was changed on the welcome page: reload so every label of the app is in that language
  if (needsReloadOnLeave()) window.location.reload();
}

export function matchRoute(e, t) {
  let [n] = e.split(`?`),
    r = n.split(`/`).filter(Boolean),
    i = t.split(`/`).filter(Boolean);
  if (r.length !== i.length) return null;
  let a = {};
  for (let e = 0; e < i.length; e++)
    if (i[e].startsWith(`:`)) a[i[e].slice(1)] = decodeURIComponent(r[e]);
    else if (r[e] !== i[e]) return null;
  return a;
}
