// Reconstructed from the StoryCore v1.7.0 compiled bundle (see DEVONLY/13_FRONTEND_SOURCE.md).
import { useWorlds, useCast, queryKeys, EXPRESSIONS } from "@/api/queries";
import * as React from "react";
import { useQueryClient, useMutation } from "@tanstack/react-query";
import { apiPost } from "@/api/legacy";
import * as Icon from "lucide-react";
import { msg, msgKey } from "@/i18n";
import { Badge, Button, EmptyState, IconButton, Input, Modal, Portrait, Spinner } from "@/components/ui";
import { cn, shortId } from "@/lib/util";
import { portraitSlot, usePortraitMap } from "@/lib/portraits";
import { useStateEditor } from "@/features/lore/schemas";

export function PickCharacterDialog({ worldId, title, onClose, onPick }) {
  let worlds = useWorlds(),
    portraitMap = usePortraitMap(),
    [o, s] = React.useState(``),
    [c, l] = React.useState(``),
    u = (worlds.data?.find((t) => t.id === worldId)?.data_json.characters ?? []).filter((e) =>
      e.name.toLowerCase().includes(o.toLowerCase()),
    );
  return (
    <Modal open onOpenChange={(e) => !e && onClose()} title={title} size="md">
      <Input
        autoFocus
        value={o}
        onChange={(e) => s(e.target.value)}
        placeholder={msg("Search characters")}
        className="mb-2"
      />

      <div className="grid max-h-80 grid-cols-2 gap-1.5 overflow-y-auto sm:grid-cols-3">
        {u.map((e) => (
          <button
            onClick={() => {
              (onPick(e.id, e.name), onClose());
            }}
            className="flex items-center gap-2 rounded-md border border-line p-1.5 text-left text-xs hover:border-accent/60"
            key={e.id}
          >
            <Portrait assetId={portraitSlot(portraitMap.data?.[e.id])} name={e.name} className="size-8 shrink-0" />
            <span className="min-w-0">
              <span className="block truncate font-medium">{e.name}</span>
              <span className="block truncate text-faint">{msgKey(e.type)}</span>
            </span>
          </button>
        ))}
      </div>
      <form
        className="mt-3 flex gap-2"
        onSubmit={(e) => {
          (e.preventDefault(), c.trim() && (onPick(null, c.trim()), onClose()));
        }}
      >
        <Input value={c} onChange={(e) => l(e.target.value)} placeholder={msg("Or a story-local character name")} />
        <Button type="submit">{msg("Add")}</Button>
      </form>
    </Modal>
  );
}

export function CastPanel({ storyId, worldId, onOpenCharacter }) {
  let cast = useCast(storyId),
    stateEditor = useStateEditor(storyId),
    queryClient = useQueryClient(),
    [o, s] = React.useState(false),
    mutation = useMutation({
      mutationFn: (t) => apiPost(`/stories/${storyId}/expressions`, t),
      onSuccess: () =>
        queryClient.invalidateQueries({
          queryKey: queryKeys.cast(storyId),
        }),
    }),
    l = (e, t) =>
      stateEditor.change.mutate({
        kind: `scene`,
        payload: t
          ? {
              present_remove: [e],
            }
          : {
              present_add: [e],
            },
      });
  return (
    <div className="space-y-3">
      <p className="text-[11px] text-faint">
        {msg(
          "Characters present in the scene or mentioned in the last replies. Click an expression to override it; lock to stop automatic suggestions.",
        )}
      </p>
      {cast.isLoading && <Spinner />}
      {cast.data?.length === 0 && (
        <EmptyState title={msg("No one in the scene yet")}>
          {msg("Add characters, or they appear here once named in the story.")}
        </EmptyState>
      )}
      {cast.data?.map((e) => (
        <CastCharacterRow
          c={e}
          onOpen={() => onOpenCharacter(e.id)}
          onSlot={(t) =>
            mutation.mutate({
              character_id: e.id,
              slot: t,
            })
          }
          onLock={() =>
            mutation.mutate({
              character_id: e.id,
              locked: !e.expression.locked,
            })
          }
          onPresent={() => l(e.id, e.present)}
          key={e.id}
        />
      ))}
      <Button size="sm" onClick={() => s(true)}>
        <Icon.UserPlus className="size-3.5" /> {msg("Add to scene")}
      </Button>
      {o && (
        <PickCharacterDialog
          worldId={worldId}
          title={msg("Add a character to the scene")}
          onClose={() => s(false)}
          onPick={(e, t) => {
            e
              ? stateEditor.change.mutate({
                  kind: `scene`,
                  payload: {
                    present_add: [e],
                  },
                })
              : stateEditor.save(
                  (e) => {
                    let n = `npc_${shortId()}`;
                    (e.npcs.push({
                      id: n,
                      name: t,
                      aliases: [],
                    }),
                      e.scene.present.push(n));
                  },
                  msg("Added local NPC {{v0}}", { v0: t }),
                );
          }}
        />
      )}
    </div>
  );
}

function CastCharacterRow({ c, onSlot, onLock, onPresent, onOpen }) {
  return (
    <div className="overflow-hidden rounded-lg border border-line">
      <div className="flex gap-3 p-2">
        <button
          onClick={onOpen}
          aria-label={msg("Open {{v0}}'s history", {
            v0: c.name,
          })}
        >
          <Portrait assetId={c.asset_id} name={c.name} variant="card" className="h-28 w-21 shrink-0" />
        </button>
        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-1">
            <div className="min-w-0">
              <p className="truncate text-[13px] font-semibold">{c.name}</p>
              <p className="truncate text-[11px] text-faint">{msgKey(c.type)}</p>
            </div>
            <IconButton
              label={c.expression.locked ? msg("Unlock expression") : msg("Lock expression")}
              active={c.expression.locked}
              onClick={onLock}
            >
              {c.expression.locked ? <Icon.Lock className="size-3.5" /> : <Icon.LockOpen className="size-3.5" />}
            </IconButton>
          </div>
          <p className="mt-1 text-[11px] text-muted">
            {EXPRESSIONS[(c.expression.slot ?? 1) - 1]?.short}
            {c.expression.source === `suggested` && (
              <span className="text-faint">
                {" "}
                {msg("· suggested")}
                {c.expression.evidence ? ` (“${c.expression.evidence}”)` : ``}
              </span>
            )}
            {c.expression.source === `extraction` && (
              <span className="text-faint"> {msg("· from scene analysis")}</span>
            )}
            {c.is_fallback && c.slot_used && (
              <span className="text-warn">
                {" "}
                {msg("· showing #")}
                {c.slot_used} {msg("(image missing)")}
              </span>
            )}
          </p>
          <div className="mt-1.5 flex flex-wrap gap-1" role="radiogroup" aria-label={`${c.name} expression`}>
            {EXPRESSIONS.map((n) => (
              <button
                role="radio"
                aria-checked={c.expression.slot === n.slot}
                title={n.name + (c.available_slots.includes(n.slot) ? `` : msg(" (no image — falls back)", {}))}
                onClick={() => onSlot(n.slot)}
                className={cn(
                  `rounded px-1.5 py-0.5 text-[10px]`,
                  c.expression.slot === n.slot ? `bg-accent text-accent-fg` : `bg-panel-2 text-muted hover:text-fg`,
                  !c.available_slots.includes(n.slot) && `opacity-50`,
                )}
                key={n.slot}
              >
                {n.short}
              </button>
            ))}
          </div>
          <button onClick={onPresent} className="mt-1.5 text-[11px] text-accent hover:underline">
            {c.present ? msg("Mark as left the scene") : msg("Mark as present")}
          </button>
          {!c.present && c.recently_mentioned && <Badge className="ml-2">{msg("mentioned")}</Badge>}
        </div>
      </div>
    </div>
  );
}
