// World creator: "Import a world (.zip)", in the creator and in the library (its own file: the library does not load
// the whole creator).
import * as React from "react";
import * as Icon from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { errorMessage } from "@/api/client";
import { msg } from "@/i18n";
import { Button, Callout, Modal, useUi } from "@/components/ui";
import { navigate } from "@/lib/router";
import { creatorApi } from "./api";

/** "Import a world (.zip)": a world shared by someone else. Also used by the library. */
export function ImportButton({ className }) {
  let queryClient = useQueryClient(),
    { toast } = useUi(),
    input = React.useRef(null),
    [busy, setBusy] = React.useState(false),
    [result, setResult] = React.useState(null);

  async function upload(file) {
    if (!file) return;
    setBusy(true);
    try {
      let r = await creatorApi.importZip(file);
      queryClient.invalidateQueries({ queryKey: [`worlds`] });
      queryClient.invalidateQueries({ queryKey: [`creator-worlds`] });
      setResult(r);
    } catch (e) {
      toast(errorMessage(e), `danger`);
    } finally {
      setBusy(false);
    }
  }

  let check = result?.check;
  return (
    <>
      <Button className={className} loading={busy} onClick={() => input.current?.click()}>
        <Icon.Upload className="size-4" /> {msg("Import a world (.zip)")}
      </Button>
      <input ref={input} type="file" accept=".zip,application/zip" hidden onChange={(e) => (upload(e.target.files?.[0]), (e.target.value = ``))} />
      {result && (
        <Modal
          open
          onOpenChange={(o) => !o && setResult(null)}
          title={msg("World imported")}
          size="sm"
          footer={
            <>
              <Button variant="ghost" onClick={() => setResult(null)}>
                {msg("Close")}
              </Button>
              <Button variant="primary" onClick={() => (setResult(null), navigate(`/library`))}>
                {msg("Open the library")}
              </Button>
            </>
          }
        >
          {check?.ok ? (
            <Callout tone="ok">{msg("The world was imported and can be played.")}</Callout>
          ) : (
            <Callout tone="warn">{msg("The world was imported, but it has errors: it may not play correctly.")}</Callout>
          )}
          {[...(check?.errors ?? []), ...(check?.warnings ?? [])].length > 0 && (
            <ul className="mt-3 list-inside list-disc text-xs text-muted">
              {[...(check?.errors ?? []), ...(check?.warnings ?? [])].slice(0, 12).map((t, i) => (
                <li key={i}>{t}</li>
              ))}
            </ul>
          )}
        </Modal>
      )}
    </>
  );
}
