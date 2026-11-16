// v1.8 phase 6: is this interface open on a paired phone (through the Wi-Fi) rather than on the computer itself?
// The computer always uses 127.0.0.1/localhost; a phone uses the computer's network address.
const LOCAL = new Set([`127.0.0.1`, `localhost`, `[::1]`, `::1`]);

export const IS_REMOTE = typeof window !== `undefined` && !LOCAL.has(window.location.hostname);
