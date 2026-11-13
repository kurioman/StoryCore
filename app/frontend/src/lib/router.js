// Reconstructed from the StoryCore v1.7.0 compiled bundle (see DEVONLY/13_FRONTEND_SOURCE.md).
import * as React from "react";

function subscribeHash(e) {
  return (window.addEventListener(`hashchange`, e), () => window.removeEventListener(`hashchange`, e));
}

export function useHashPath() {
  return React.useSyncExternalStore(subscribeHash, () => window.location.hash.replace(/^#/, ``) || `/`);
}

export function navigate(e) {
  window.location.hash.replace(/^#/, ``) !== e && (window.location.hash = e);
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
