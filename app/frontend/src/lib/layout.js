// StoryCore mobile (Phase 2): the phone layout of the play screen.
// Used in the Android app and on a phone paired over Wi-Fi, on screens narrower than a tablet. The computer (and a
// narrow window on the computer) keeps its own layout.
import * as React from "react";
import { useMediaQuery } from "@/lib/hooks";
import { IS_PHONE } from "@/lib/remote";

export function usePhoneLayout() {
  let narrow = useMediaQuery(`(max-width: 767px)`);
  return IS_PHONE && narrow;
}

// The phone play screen has a single top bar: its ☰ and "?" buttons ask the app shell (app/App.jsx) to open the
// library drawer and the help, which the shell owns.
const OPEN_LIBRARY = `storycore:open-library`;
const OPEN_HELP = `storycore:open-help`;

export const openLibrary = () => window.dispatchEvent(new Event(OPEN_LIBRARY));
export const openHelp = () => window.dispatchEvent(new Event(OPEN_HELP));

export function useShellRequests(onLibrary, onHelp) {
  React.useEffect(() => {
    window.addEventListener(OPEN_LIBRARY, onLibrary);
    window.addEventListener(OPEN_HELP, onHelp);
    return () => {
      window.removeEventListener(OPEN_LIBRARY, onLibrary);
      window.removeEventListener(OPEN_HELP, onHelp);
    };
  }, [onLibrary, onHelp]);
}
