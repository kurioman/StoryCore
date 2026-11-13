// Reconstructed from the StoryCore v1.7.0 compiled bundle (see DEVONLY/13_FRONTEND_SOURCE.md).
import { useInvalidateStory } from "@/api/queries";
import * as React from "react";
import { apiPost, errorMessage } from "@/api/legacy";
import * as Icon from "lucide-react";
import { msg, msgKey } from "@/i18n";
import {
  Badge,
  Button,
  EmptyState,
  ErrorCallout,
  Modal,
  Portrait,
  SectionTitle,
  Spinner,
  useUi,
} from "@/components/ui";
import { PickCharacterDialog } from "@/features/story/panels/CastPanel";
import { StatusList } from "@/features/story/panels/StatusPanel";
import { cn, timeAgo } from "@/lib/util";
import { relationEventSchema, useKnownCharacter, useKnownCharacters } from "@/features/story/api";

var KNOWLEDGE_LABELS = {
    rumored: msg("Heard of", {}),
    encountered: msg("Met", {}),
    known: msg("Known", {}),
    removed: msg("Removed", {}),
  },
  KNOWLEDGE_TONES = {
    rumored: `neutral`,
    encountered: `info`,
    known: `ok`,
  };

export function KnownPanel({ storyId, worldId, focus, setFocus, onOpenJournal }) {
  let knownCharacters = useKnownCharacters(storyId),
    invalidateStory = useInvalidateStory(),
    { toast } = useUi(),
    [c, l] = React.useState(false),
    u = async (t, n, r) => {
      try {
        (await apiPost(`/stories/${storyId}/characters`, {
          character_id: t,
          status: n,
          note: r,
        }),
          invalidateStory(storyId));
      } catch (e) {
        toast(errorMessage(e), `danger`);
      }
    };
  return (
    <div className="space-y-2">
      <p className="text-[11px] text-faint">
        {msg(
          "Characters your protagonist has heard of, met or knows in this story. The full catalogue stays in the Lore library.",
        )}
      </p>
      {knownCharacters.isLoading && <Spinner />}
      {knownCharacters.isError && (
        <ErrorCallout error={knownCharacters.error} onRetry={() => knownCharacters.refetch()} />
      )}
      {knownCharacters.data?.length === 0 && (
        <EmptyState title={msg("Nobody discovered yet")}>
          {msg("Characters appear here when the story introduces them, or add one yourself.")}
        </EmptyState>
      )}
      {knownCharacters.data?.map((e) => (
        <KnownCharacterRow c={e} onOpen={() => setFocus(e.character_id)} key={e.character_id} />
      ))}
      <Button size="sm" onClick={() => l(true)}>
        <Icon.UserPlus className="size-3.5" /> {msg("Mark someone as known")}
      </Button>
      {c && (
        <PickCharacterDialog
          worldId={worldId}
          title={msg("Your protagonist knows…")}
          onClose={() => l(false)}
          onPick={(e, t) => {
            e
              ? u(e, `known`, msg("Added manually", {}))
              : toast(
                  msg("Add “{{v0}}” as a story-local character in the Cast tab first, then mark them here.", {
                    v0: t,
                  }),
                  `warn`,
                );
          }}
        />
      )}
      {focus && (
        <KnownCharacterDetail
          storyId={storyId}
          cid={focus}
          onClose={() => setFocus(null)}
          onStatus={u}
          onOpenJournal={onOpenJournal}
        />
      )}
    </div>
  );
}

function KnownCharacterRow({ c, onOpen }) {
  let n = c.relationship;
  return (
    <button
      onClick={onOpen}
      className={cn(
        `flex w-full gap-2.5 rounded-md border p-2 text-left hover:border-line-strong`,
        c.in_scene ? `border-accent/50` : `border-line`,
      )}
    >
      <Portrait assetId={c.asset_id} name={c.name} className="size-10 shrink-0" />
      <div className="min-w-0 flex-1">
        <div className="flex items-center justify-between gap-1">
          <span className="truncate text-[13px] font-medium">{c.name}</span>
          <Badge tone={KNOWLEDGE_TONES[c.status]}>{KNOWLEDGE_LABELS[c.status]}</Badge>
        </div>
        <p className="truncate text-[11px] text-faint">
          {c.in_scene && <span className="text-accent">{msg("in scene ·")} </span>}
          {n
            ? `${n.label || `—`} · ${Object.entries(n.axes)
                .map(([e, t]) => `${e} ${t}`)
                .join(`, `)}`
            : msg("No relationship tracked")}
        </p>
        <p className="truncate text-[10px] text-faint">
          {c.source_seq == null
            ? c.capture_method === `scene`
              ? msg("placed in the scene")
              : c.capture_method
            : msg("since #{{v0}}", {
                v0: c.source_seq,
              })}
          {c.evidence ? ` · “${c.evidence}”` : ``}
        </p>
      </div>
    </button>
  );
}

function KnownCharacterDetail({ storyId, cid, onClose, onStatus, onOpenJournal }) {
  let knownCharacter = useKnownCharacter(storyId, cid),
    o = useKnownCharacters(storyId).data?.find((e) => e.character_id === cid),
    s = knownCharacter.data?.character.name ?? o?.name ?? cid,
    c = knownCharacter.data?.relationship;
  return (
    <Modal
      open
      onOpenChange={(e) => !e && onClose()}
      title={s}
      size="md"
      footer={
        <Button
          variant="ghost"
          className="mr-auto"
          onClick={() => {
            (onClose(), onOpenJournal(cid));
          }}
        >
          <Icon.BookOpen className="size-3.5" /> {msg("Journal entries")}
        </Button>
      }
    >
      {knownCharacter.isLoading && <Spinner />}
      {knownCharacter.isError && <ErrorCallout error={knownCharacter.error} onRetry={() => knownCharacter.refetch()} />}
      {knownCharacter.data && (
        <div className="space-y-3 text-[13px]">
          <div className="flex gap-3">
            <Portrait assetId={o?.asset_id} name={s} variant="card" className="h-32 w-24 shrink-0" />
            <div className="min-w-0 flex-1 space-y-2">
              <p className="text-[11px] text-faint">
                {msgKey(knownCharacter.data.character.type)}
                {knownCharacter.data.character.local ? msg(" · story-local") : ``}
              </p>
              <div className="flex flex-wrap gap-1" role="radiogroup" aria-label={msg("What the protagonist knows")}>
                {relationEventSchema.map((e) => (
                  <Button
                    size="sm"
                    variant={o?.status === e ? `primary` : `secondary`}
                    role="radio"
                    aria-checked={o?.status === e}
                    onClick={() => onStatus(cid, e, msg("Corrected manually", {}))}
                    key={e}
                  >
                    {KNOWLEDGE_LABELS[e]}
                  </Button>
                ))}
                {o && (
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={async () => {
                      (await onStatus(cid, `removed`, msg("Removed manually", {})), onClose());
                    }}
                  >
                    {msg("Remove")}
                  </Button>
                )}
              </div>
              {c ? (
                <p>
                  <Badge>{c.label || `—`}</Badge>{" "}
                  <span className="text-[12px] text-muted">
                    {Object.entries(c.axes)
                      .map(([e, t]) => `${e} ${t}`)
                      .join(` · `)}
                  </span>
                  {c.note && <span className="mt-1 block text-[12px] text-muted">{c.note}</span>}
                </p>
              ) : (
                <p className="text-[12px] text-faint">{msg("No relationship tracked yet (Relations tab).")}</p>
              )}
            </div>
          </div>
          <SectionTitle>{msg("Relationship changes")}</SectionTitle>
          <ol className="max-h-40 space-y-1 overflow-y-auto">
            {(c?.history ?? [])
              .slice()
              .reverse()
              .map((e, t) => (
                <li className="text-xs text-muted" key={t}>
                  <span className="text-faint">{timeAgo(e.at)}</span>
                  {" · "}
                  {e.change} <Badge>{msgKey(e.source)}</Badge>
                  {e.reason && (
                    <span className="text-faint">
                      {" — "}
                      {e.reason}
                    </span>
                  )}
                  {e.source_replaced && (
                    <span className="block text-warn">
                      {msg(
                        "The reply this came from was regenerated or deleted; the change is still applied. Adjust it in the Relations tab if it should not count.",
                      )}
                    </span>
                  )}
                </li>
              ))}
            {knownCharacter.data.relationship_proposals.map((e) => (
              <li className="text-xs text-muted" key={e.id}>
                <Badge tone={e.status === `pending` ? `accent` : e.status === `accepted` ? `ok` : `neutral`}>
                  {e.status}
                </Badge>{" "}
                {String(e.payload_json.axis ?? ``)}{" "}
                {e.payload_json.delta == null
                  ? ``
                  : Number(e.payload_json.delta) > 0
                    ? `+${e.payload_json.delta}`
                    : String(e.payload_json.delta)}
                {" — "}
                {e.rationale}
                {e.source_seqs.length > 0 && (
                  <span className="text-faint">
                    {" (#"}
                    {e.source_seqs.join(`, #`)})
                  </span>
                )}
              </li>
            ))}
            {!c?.history?.length && !knownCharacter.data.relationship_proposals.length && (
              <li className="text-xs text-faint">{msg("No changes recorded.")}</li>
            )}
          </ol>
          {(knownCharacter.data.character_relationships.length > 0 ||
            knownCharacter.data.lore_relationships.length > 0) && (
            <>
              <SectionTitle>{msg("With other characters")}</SectionTitle>
              <ul className="space-y-1" aria-label={msg("Relationships between characters")}>
                {knownCharacter.data.character_relationships.map((e, t) => (
                  <li className="text-xs text-muted" key={`s${t}`}>
                    <Badge tone="accent">{msg("story")}</Badge> {e.source_name}
                    {" → "}
                    {e.target_name}
                    {": "}
                    {e.label}
                    {Object.entries(e.axes).filter(([, e]) => e).length > 0 && (
                      <span className="text-faint">
                        {" ("}
                        {Object.entries(e.axes)
                          .filter(([, e]) => e)
                          .map(([e, t]) => `${e} ${t}`)
                          .join(`, `)}
                        )
                      </span>
                    )}
                  </li>
                ))}
                {knownCharacter.data.lore_relationships.map((e, t) => (
                  <li
                    className="text-xs text-muted"
                    title={msg("From lore ({{v0}}); background only — the protagonist may not know this", {
                      v0: e.lore_source,
                    })}
                    key={`l${t}`}
                  >
                    <Badge>{msg("lore")}</Badge> {e.source_name}
                    {" → "}
                    {e.target_name}
                    {": "}
                    {msgKey(e.type)}
                    {e.confidence !== `high` && (
                      <span className="text-faint">
                        {" · "}
                        {msg("{{v0}} confidence", { v0: msgKey(e.confidence) })}
                      </span>
                    )}
                  </li>
                ))}
              </ul>
              <p className="mt-1 text-[11px] text-faint">
                {msg(
                  "“Lore” is the starting background from the lore pack; “story” is what has changed in play (A → B is A's view of B).",
                )}
              </p>
            </>
          )}
          {knownCharacter.data.canon.length > 0 && (
            <>
              <SectionTitle>{msg("Canon facts")}</SectionTitle>
              <ul className="space-y-1" aria-label={msg("Canon facts")}>
                {knownCharacter.data.canon.map((e, t) => (
                  <li
                    className="text-xs text-muted"
                    title={msg("Source: {{v0}}", {
                      v0: e.source,
                    })}
                    key={t}
                  >
                    <Badge tone={e.status === `verified` ? undefined : `warn`}>
                      {e.source.startsWith(`lore`) ? `lore` : `confirmed`}
                    </Badge>{" "}
                    {e.text}
                    {e.status !== `verified` && <span className="text-warn"> {msg("· needs your confirmation")}</span>}
                  </li>
                ))}
              </ul>
              <p className="mt-1 text-[11px] text-faint">
                {msg("Facts about who")} {s}{" "}
                {msg("is (family, classes). They never change relationship values; the protagonist may not know them.")}
              </p>
            </>
          )}
          <SectionTitle>
            {msg("What")} {s} {msg("knows")}
          </SectionTitle>
          <StatusList title={msg("Knows")} items={knownCharacter.data.knowledge.knows} />
          <StatusList
            title={msg("Believes / suspects (may be wrong)")}
            items={knownCharacter.data.knowledge.believes}
          />

          <StatusList title={msg("Does not know")} items={knownCharacter.data.knowledge.unaware} />
          {!knownCharacter.data.knowledge.knows.length &&
            !knownCharacter.data.knowledge.believes.length &&
            !knownCharacter.data.knowledge.unaware.length && (
              <p className="text-xs text-faint">
                {msg(
                  "No recorded knowledge yet. Facts and secrets captured in the journal appear here for the characters who know them.",
                )}
              </p>
            )}
          <SectionTitle>{msg("Discovery history")}</SectionTitle>
          <ol className="space-y-1">
            {knownCharacter.data.discovery_history.map((e) => (
              <li className="text-xs text-muted" key={e.id}>
                <Badge>{KNOWLEDGE_LABELS[e.status] ?? e.status}</Badge>{" "}
                {e.source_seq != null && (
                  <span className="text-faint">
                    #{e.source_seq}
                    {" · "}
                  </span>
                )}
                {e.capture_method} {e.evidence && <span className="text-faint">— “{e.evidence}”</span>}
              </li>
            ))}
            {!knownCharacter.data.discovery_history.length && (
              <li className="text-xs text-faint">
                {o?.capture_method === `scene`
                  ? msg("Placed in the scene (not yet recorded as a discovery).")
                  : msg("No records.")}
              </li>
            )}
          </ol>
        </div>
      )}
    </Modal>
  );
}
