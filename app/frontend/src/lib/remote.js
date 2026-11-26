// v0.5 phase 6: is this interface open on a paired phone (through the Wi-Fi) rather than on the computer itself?
// The computer always uses 127.0.0.1/localhost; a phone uses the computer's network address.
const LOCAL = new Set([`127.0.0.1`, `localhost`, `[::1]`, `::1`]);

export const IS_REMOTE = typeof window !== `undefined` && !LOCAL.has(window.location.hostname);

// StoryCore mobile: is this interface running inside the Android app (mobile/android)? Its WebView adds
// "StoryCoreAndroid/<version>" to the user agent. The app owns its data like the computer does (providers, imports,
// backups stay available), but the computer-only things are hidden: Ollama / LM Studio, "Play on a phone",
// graphics-card advice, "Open data folder".
export const IS_ANDROID_APP = typeof navigator !== `undefined` && /\bStoryCoreAndroid\//.test(navigator.userAgent);
// Version of the installed Android app (the published version it was built for), or "" outside the app.
export const ANDROID_APP_VERSION = IS_ANDROID_APP
  ? (navigator.userAgent.match(/\bStoryCoreAndroid\/([0-9][^\s]*)/)?.[1] ?? ``)
  : ``;

// The phone interface (touch, small screen): the Android app or a phone paired over Wi-Fi.
export const IS_PHONE = IS_ANDROID_APP || IS_REMOTE;
