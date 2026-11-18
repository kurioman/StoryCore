// World creator (Phase 8) at #/creator: the player's worlds, a new world, a copy of an existing world, or a shared
// world (.zip) to import. One world is edited at #/creator/<id> (WorldEditor.jsx).
import * as React from "react";
import * as Icon from "lucide-react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { errorMessage } from "@/api/client";
import { msg } from "@/i18n";
import { Button, Callout, ErrorCallout, Field, Input, Modal, Spinner, useUi } from "@/components/ui";
import { navigate } from "@/lib/router";
import { creatorApi } from "./api";
import { ImportButton } from "./ImportButton";
import { WorldEditor } from "./WorldEditor";

export function CreatorPage({ worldId }) {
  return worldId ? <WorldEditor worldId={worldId} key={worldId} /> : <WorldList />;
}

function WorldList() {
  let worlds = useQuery({ queryKey: [`creator-worlds`], queryFn: creatorApi.list }),
    mine = (worlds.data ?? []).filter((w) => w.editable),
    others = (worlds.data ?? []).filter((w) => !w.editable),
    [naming, setNaming] = React.useState(null); // {copyFrom, name} while the "name your world" window is open

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-5xl px-6 py-8">
        <header className="mb-2 flex flex-wrap items-center gap-3">
          <Icon.PencilRuler className="size-7 text-accent" />
          <h1 className="text-2xl font-semibold">{msg("World creator")}</h1>
          <div className="ml-auto flex gap-2">
            <ImportButton />
            <Button variant="primary" onClick={() => setNaming({ copyFrom: ``, name: `` })}>
              <Icon.Plus className="size-4" /> {msg("Create a world")}
            </Button>
          </div>
        </header>
        <p className="mb-8 max-w-3xl text-sm leading-relaxed text-muted">
          {msg("Invent your own world: its characters, places, groups and the ways a story can begin. No technical knowledge is needed, and the AI can write drafts for you. Your worlds appear in the library like the others, and you can share them as a single .zip file.")}
        </p>

        {worlds.isLoading && <Spinner />}
        {worlds.error && <ErrorCallout error={worlds.error} onRetry={() => worlds.refetch()} />}

        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-muted">{msg("My worlds")}</h2>
        {worlds.data && !mine.length && <p className="mb-8 text-sm text-faint">{msg("You have not created a world yet.")}</p>}
        <div className="mb-10 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {mine.map((w) => (
            <button
              key={w.id}
              onClick={() => navigate(`/creator/${w.id}`)}
              className="flex flex-col rounded-lg border border-line bg-panel p-4 text-left hover:border-accent/60"
            >
              <span className="flex items-center gap-2 font-semibold">
                <Icon.Globe className="size-4 text-accent" /> {w.name}
              </span>
              {w.summary && <span className="mt-1.5 line-clamp-3 text-xs text-muted">{w.summary}</span>}
              <span className="mt-auto pt-3 text-xs text-accent">{msg("Edit")} →</span>
            </button>
          ))}
        </div>

        {others.length > 0 && (
          <>
            <h2 className="mb-1 text-sm font-semibold uppercase tracking-wider text-muted">{msg("Start from an existing world")}</h2>
            <p className="mb-3 text-xs text-faint">
              {msg("These worlds are not edited directly: make your own copy and change it as you like. The original stays as it is.")}
            </p>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {others.map((w) => (
                <div key={w.id} className="flex flex-col rounded-lg border border-line bg-panel p-4">
                  <span className="font-semibold">{w.name}</span>
                  {w.summary && <span className="mt-1.5 line-clamp-3 text-xs text-muted">{w.summary}</span>}
                  <Button
                    size="sm"
                    className="mt-3 self-start"
                    onClick={() => setNaming({ copyFrom: w.id, name: msg("{{v0}} (my version)", { v0: w.name }) })}
                  >
                    <Icon.Copy className="size-3.5" /> {msg("Make a copy")}
                  </Button>
                </div>
              ))}
            </div>
          </>
        )}
      </div>
      {naming && <NameWorld start={naming} onClose={() => setNaming(null)} />}
    </div>
  );
}

function NameWorld({ start, onClose }) {
  let queryClient = useQueryClient(),
    [name, setName] = React.useState(start.name),
    [busy, setBusy] = React.useState(false),
    [error, setError] = React.useState(``);

  async function go() {
    setBusy(true);
    setError(``);
    try {
      let r = await creatorApi.create(name, start.copyFrom);
      queryClient.invalidateQueries({ queryKey: [`worlds`] });
      queryClient.invalidateQueries({ queryKey: [`creator-worlds`] });
      navigate(`/creator/${r.id}`);
    } catch (e) {
      setError(errorMessage(e));
      setBusy(false);
    }
  }

  return (
    <Modal
      open
      onOpenChange={(o) => !o && !busy && onClose()}
      title={start.copyFrom ? msg("Copy a world") : msg("Create a world")}
      size="sm"
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={busy}>
            {msg("Cancel")}
          </Button>
          <Button variant="primary" onClick={go} loading={busy} disabled={!name.trim()}>
            {start.copyFrom ? msg("Make a copy") : msg("Create")}
          </Button>
        </>
      }
    >
      <Field label={msg("Name of the world")} hint={msg("You can change it later.")}>
        <Input autoFocus value={name} onChange={(e) => setName(e.target.value)} onKeyDown={(e) => e.key === `Enter` && name.trim() && go()} />
      </Field>
      {start.copyFrom && <p className="mt-2 text-xs text-faint">{msg("Copying a big world with its pictures can take a few seconds.")}</p>}
      {error && <Callout tone="danger" className="mt-3">{error}</Callout>}
    </Modal>
  );
}
