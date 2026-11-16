// "Play on a phone" (v0.5, phase 6), at #/mobile and in Settings: opens StoryCore to the Wi-Fi on request and shows the
// QR code a phone scans to pair (backend: services/remote.py). Only ever shown on the computer itself.
import * as React from "react";
import * as Icon from "lucide-react";
import QRCode from "qrcode";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiDelete, apiGet, apiPost, errorMessage } from "@/api/legacy";
import { msg } from "@/i18n";
import { Button, Callout, ErrorCallout, SectionTitle, Spinner, Toggle, useUi } from "@/components/ui";

const KEY = [`remote-status`];

function QrImage({ text }) {
  let [src, setSrc] = React.useState(null);
  React.useEffect(() => {
    let alive = true;
    QRCode.toDataURL(text, { margin: 1, width: 240, color: { dark: `#0b1224`, light: `#ffffff` } })
      .then((url) => alive && setSrc(url))
      .catch(() => alive && setSrc(null));
    return () => {
      alive = false;
    };
  }, [text]);
  return (
    <div className="grid size-[240px] place-items-center rounded-xl bg-white p-2 shadow-lg">
      {src ? <img src={src} alt={msg("QR code to scan with the phone")} className="size-full" /> : <Spinner />}
    </div>
  );
}

function minutes(seconds) {
  return Math.max(1, Math.ceil(seconds / 60));
}

function ago(ts) {
  let s = Math.max(0, Math.round(Date.now() / 1000 - ts));
  if (s < 60) return msg("just now");
  return msg("{{v0}} min ago", { v0: Math.round(s / 60) });
}

export function PhonePanel() {
  let queryClient = useQueryClient(),
    { toast } = useUi(),
    [busy, setBusy] = React.useState(false),
    status = useQuery({
      queryKey: KEY,
      queryFn: () => apiGet(`/remote/status`),
      refetchInterval: (q) => (q.state.data?.enabled ? 3000 : false),
    }),
    st = status.data;

  async function call(fn) {
    setBusy(true);
    try {
      queryClient.setQueryData(KEY, await fn());
    } catch (e) {
      toast(errorMessage(e), `danger`);
    } finally {
      setBusy(false);
    }
  }

  if (status.isLoading) return <Spinner />;
  if (status.isError) return <ErrorCallout error={status.error} onRetry={() => status.refetch()} />;

  let url = st.urls?.[0],
    code = st.code ? `${st.code.slice(0, 3)} ${st.code.slice(3)}` : null;

  return (
    <div className="max-w-3xl space-y-5">
      <p className="text-sm text-muted">
        {msg("Play from your phone or tablet: the story runs on this computer, the phone only shows it. Both must be on the same Wi-Fi.")}
      </p>

      <div className="rounded-xl border border-line bg-panel p-4">
        <Toggle
          checked={st.enabled}
          disabled={busy}
          onChange={(on) => call(() => apiPost(on ? `/remote/enable` : `/remote/disable`))}
          label={msg("Allow a phone to connect")}
          description={msg("Switches itself off when StoryCore closes. Switching it off disconnects every phone.")}
        />
      </div>

      {st.enabled && (
        <>
          {url ? (
            <div className="flex flex-col items-center gap-5 rounded-xl border border-line bg-panel p-5 sm:flex-row sm:items-start">
              <QrImage text={`${url}/pair?code=${st.code ?? ``}`} />
              <ol className="min-w-0 flex-1 list-decimal space-y-3 pl-5 text-sm">
                <li>{msg("Connect the phone to the same Wi-Fi as this computer.")}</li>
                <li>{msg("Open the phone's camera and point it at the QR code, then open the link.")}</li>
                <li>
                  {msg("Or type this address in the phone's browser:")}
                  <div className="mt-1 select-all break-all font-mono text-base text-accent">{url}</div>
                  {msg("then enter the code:")}
                  <div className="mt-1 font-mono text-2xl tracking-[0.3em] text-fg">{code ?? `—`}</div>
                  <div className="text-xs text-faint">
                    {msg("Valid for {{v0}} min, works once.", { v0: minutes(st.code_valid_for) })}{" "}
                    <button
                      type="button"
                      className="underline hover:text-fg"
                      disabled={busy}
                      onClick={() => call(() => apiPost(`/remote/new-code`))}
                    >
                      {msg("New code")}
                    </button>
                  </div>
                </li>
              </ol>
            </div>
          ) : (
            <Callout tone="warn" title={msg("No network address found")}>
              {msg("This computer does not seem to be connected to a network. Connect it to your Wi-Fi or box, then switch the option off and on again.")}
            </Callout>
          )}

          <Callout tone="info" title={msg("The phone cannot open the page?")}>
            {msg("The first time, Windows may ask whether StoryCore can use the network: tick \"Private networks\" and click \"Allow\". Also check that the phone is not on mobile data or on a guest Wi-Fi.")}
          </Callout>
          <Callout tone="warn" title={msg("Only on your home Wi-Fi")}>
            {msg("The link between the phone and this computer is not encrypted. Do not use this on a public Wi-Fi (café, station, hotel).")}
          </Callout>

          <div>
            <SectionTitle
              action={
                st.devices.length > 0 && (
                  <Button size="sm" variant="ghost" disabled={busy} onClick={() => call(() => apiPost(`/remote/forget-all`))}>
                    <Icon.LogOut className="size-3.5" /> {msg("Disconnect all")}
                  </Button>
                )
              }
            >
              {msg("Connected devices")}
            </SectionTitle>
            {st.devices.length === 0 ? (
              <p className="text-sm text-faint">{msg("No phone connected yet.")}</p>
            ) : (
              <ul className="divide-y divide-line rounded-xl border border-line bg-panel">
                {st.devices.map((d) => (
                  <li key={d.id} className="flex items-center gap-3 px-4 py-2.5 text-sm">
                    <Icon.Smartphone className="size-4 text-accent" />
                    <span className="flex-1">{d.name === `?` ? msg("Unknown device") : d.name}</span>
                    <span className="text-xs text-faint">{msg("Active {{v0}}", { v0: ago(d.last_seen) })}</span>
                    <Button
                      size="sm"
                      variant="ghost"
                      disabled={busy}
                      onClick={() => call(() => apiDelete(`/remote/devices/${d.id}`))}
                    >
                      {msg("Disconnect")}
                    </Button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </>
      )}
    </div>
  );
}
