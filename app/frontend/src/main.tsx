// Cinzel (SIL Open Font License 1.1, bundled with the app): the StoryCore name and the welcome title.
import "@fontsource/cinzel/latin-700.css";
import "@fontsource/cinzel/latin-900.css";
import "./styles.css";
import { IS_ANDROID_APP, IS_PHONE } from "./lib/remote";
import "./i18n";
// StoryCore mobile: lets styles.css adapt to the Android app / a paired phone (html[data-platform=...])
if (IS_PHONE) document.documentElement.dataset.platform = IS_ANDROID_APP ? `android` : `phone`;
import "./app/App";
