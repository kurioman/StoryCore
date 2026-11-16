// "Report a problem" (v1.8): the player describes what happened, and the bug report zip is downloaded with that
// text inside (description.txt) and where they were (context.json: page, story id). Never any story text.
import * as React from "react";
import { IS_REMOTE } from "@/lib/remote";
import * as Icon from "lucide-react";
import { msg } from "@/i18n";
import { Button, Modal, Textarea, useUi } from "@/components/ui";
import { cn } from "@/lib/util";

/** Downloads the bug report zip. Resolves when the file has been handed to the browser. */
export async function downloadBugReport({ description, storyId } = {}) {
  let res = await fetch(`/api/system/bug-report`, {
    method: `POST`,
    headers: { "Content-Type": `application/json`, "X-Story-Client": `1` },
    body: JSON.stringify({
      description: description || null,
      story_id: storyId || null,
      page: window.location.hash.replace(/^#/, ``) || `/`,
    }),
  });
  if (!res.ok) throw Error(msg("The bug report could not be made (error {{v0}}).", { v0: res.status }));
  let name =
    /filename="([^"]+)"/.exec(res.headers.get(`content-disposition`) ?? ``)?.[1] ?? `StoryCore_bug_report.zip`;
  let url = URL.createObjectURL(await res.blob()),
    link = document.createElement(`a`);
  link.href = url;
  link.download = name;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
  return name;
}

export function ReportProblemDialog({ open, onClose, storyId }) {
  let { toast } = useUi(),
    [text, setText] = React.useState(``),
    [busy, setBusy] = React.useState(false);
  React.useEffect(() => {
    if (open) setText(``);
  }, [open]);
  async function send() {
    setBusy(true);
    try {
      let name = await downloadBugReport({ description: text, storyId });
      toast(msg("Bug report saved: {{v0}}. Send this file to the StoryCore team.", { v0: name }));
      onClose();
    } catch (e) {
      toast(e instanceof Error ? e.message : String(e), `danger`);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal
      open={open}
      onOpenChange={(o) => !o && onClose()}
      title={msg("Report a problem")}
      description={msg("A zip file will be downloaded. Send it to the StoryCore team with your message.")}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            {msg("Cancel")}
          </Button>
          <button
            type="button"
            disabled={busy}
            onClick={send}
            className="sc-action sc-action-red inline-flex h-8.5 items-center gap-1.5 rounded-md px-3 text-sm font-medium disabled:opacity-60"
          >
            {busy ? <Icon.LoaderCircle className="size-3.5 animate-spin" /> : <Icon.Download className="size-3.5" />}{" "}
            {msg("Export the bug report")}
          </button>
        </>
      }
    >
      <label htmlFor="report-problem-text" className="mb-1.5 block text-sm font-medium">
        {msg("What happened?")}
      </label>
      <Textarea
        id="report-problem-text"
        autoFocus
        rows={6}
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder={msg("What you did, what you expected, and what happened instead.")}
      />
      <p className="mt-3 flex gap-2 text-xs text-muted">
        <Icon.ShieldCheck className="mt-0.5 size-3.5 shrink-0 text-ok" />
        {msg(
          "Inside: your message, versions, the app log, settings and AI models. Never inside: API keys, story text or titles, notes or lore.",
        )}
      </p>
    </Modal>
  );
}

/** The two buttons at the bottom of the play screen's right panel: golden Recap, red Report a problem. */
export function StoryPanelActions({ storyId, onRecap, className }) {
  let [open, setOpen] = React.useState(false);
  return (
    <div className={cn(`grid gap-2 p-3`, IS_REMOTE ? `grid-cols-1` : `grid-cols-2`, className)}>
      <button
        type="button"
        onClick={onRecap}
        title={msg("Recap the story (/recap)")}
        className="sc-action sc-action-gold inline-flex h-10 items-center justify-center gap-2 rounded-lg text-sm font-medium"
      >
        <Icon.ScrollText className="size-4" /> {msg("Recap")}
      </button>
      {/* the bug report reads the computer's logs: offered on the computer only (v1.8) */}
      {!IS_REMOTE && <button
        type="button"
        onClick={() => setOpen(true)}
        title={msg("Export a bug report with a description of the problem")}
        className="sc-action sc-action-red inline-flex h-10 items-center justify-center gap-2 rounded-lg text-sm font-medium"
      >
        <Icon.Bug className="size-4" /> {msg("Report a problem")}
      </button>}
      <ReportProblemDialog open={open} onClose={() => setOpen(false)} storyId={storyId} />
    </div>
  );
}
