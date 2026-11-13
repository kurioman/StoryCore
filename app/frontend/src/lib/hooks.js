// Reconstructed from the StoryCore v1.7.0 compiled bundle (see DEVONLY/13_FRONTEND_SOURCE.md).
import * as React from "react";

export function useLocalState(e, t) {
  let [n, r] = React.useState(() => {
    try {
      let n = localStorage.getItem(`lsd:${e}`);
      return n ? JSON.parse(n) : t;
    } catch {
      return t;
    }
  });
  return (
    React.useEffect(() => {
      try {
        localStorage.setItem(`lsd:${e}`, JSON.stringify(n));
      } catch {}
    }, [e, n]),
    [n, r]
  );
}

export function useMediaQuery(e) {
  let [t, n] = React.useState(() => window.matchMedia(e).matches);
  return (
    React.useEffect(() => {
      let t = window.matchMedia(e),
        r = () => n(t.matches);
      return (t.addEventListener(`change`, r), () => t.removeEventListener(`change`, r));
    }, [e]),
    t
  );
}
