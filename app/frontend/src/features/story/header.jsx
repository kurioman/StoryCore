// Reconstructed from the StoryCore v1.7.0 compiled bundle (see DEVONLY/13_FRONTEND_SOURCE.md).
import * as React from "react";
import { useInvalidateStory, useAvatars, useProviders, useSettings, queryKeys } from "@/api/queries";
import { useMutation, useIsMutating, useMutationState, useQueryClient } from "@tanstack/react-query";
import { apiPatch, apiPost, errorMessage, apiDelete } from "@/api/legacy";
import * as Icon from "lucide-react";
import { msg } from "@/i18n";
import {
  Badge,
  Button,
  IconButton,
  Input,
  Popover,
  PopoverContent,
  PopoverTrigger,
  Select,
  UploadedImage,
  useUi,
} from "@/components/ui";
import { ContextWarnings } from "@/features/story/composer";
import { UsageMeter } from "@/features/story/UsageMeter";
import { CodexButton } from "@/features/codex/CodexDialog";
import { cn, isCloudModelId } from "@/lib/util";
import { navigate } from "@/lib/router";
import { presetName } from "@/lib/presets";
import { openHelp, openLibrary, usePhoneLayout } from "@/lib/layout";

var WIDE_HEADER = 960;

function useIsWide() {
  let e = React.useRef(null),
    [t, n] = React.useState(false);
  return (
    React.useLayoutEffect(() => {
      let t = e.current;
      if (!t || typeof ResizeObserver > `u`) return;
      let r = () => n(t.clientWidth < WIDE_HEADER);
      r();
      let i = new ResizeObserver(r);
      return (i.observe(t), () => i.disconnect());
    }, []),
    [e, t]
  );
}

export function StoryHeader({
  story,
  branches,
  manifest,
  view,
  setView,
  rightOpen,
  setRightOpen,
  reviewCount,
  generating,
  onOpen,
}) {
  let [u, d] = React.useState(story.title),
    [f, p] = React.useState(false),
    invalidateStory = useInvalidateStory(),
    mutation = useMutation({
      mutationFn: () =>
        apiPatch(`/stories/${story.id}`, {
          title: u,
        }),
      onSuccess: () => invalidateStory(story.id),
    }),
    [v, y] = useIsWide(),
    phone = usePhoneLayout();
  if (phone)
    return (
      <PhoneStoryHeader
        story={story}
        branches={branches}
        view={view}
        setView={setView}
        rightOpen={rightOpen}
        setRightOpen={setRightOpen}
        reviewCount={reviewCount}
        generating={generating}
        onOpen={onOpen}
        title={u}
        setTitle={d}
        editing={f}
        setEditing={p}
        saveTitle={() => mutation.mutate()}
      />
    );
  return (
    <header ref={v} className="flex h-12 shrink-0 items-center gap-1 border-b border-line px-2 sm:px-3">
      {f ? (
        <form
          onSubmit={(e) => {
            (e.preventDefault(), mutation.mutate(), p(false));
          }}
        >
          <Input
            autoFocus
            value={u}
            onChange={(e) => d(e.target.value)}
            onBlur={() => p(false)}
            className="h-7 w-56"
            aria-label={msg("Story title")}
          />
        </form>
      ) : (
        <button
          onClick={() => p(true)}
          className="min-w-16 max-w-[14rem] truncate rounded px-1.5 py-1 text-[15px] font-semibold hover:bg-panel-2"
          title={msg("Rename story")}
        >
          {story.title}
        </button>
      )}
      <BranchMenu story={story} branches={branches} disabled={generating} />
      {!y && (
        <>
          <div className="mx-1 h-5 w-px bg-line" />
          <div className="flex items-center gap-1">
            <AvatarSwitch story={story} />
            <ModelSwitch story={story} />
            <StoryOptions story={story} />
          </div>
        </>
      )}
      <div className="ml-auto flex shrink-0 items-center gap-1">
        <ContextWarnings manifest={manifest} onClick={() => onOpen(`context`)} />
        <UsageMeter storyId={story.id} refreshKey={`${generating ? 1 : 0}:${story.updated_at ?? ``}`} />
        <SaveStatus />
        <MoreToolsMenu story={story} onOpen={onOpen} compact={y} />
        <CodexButton storyId={story.id} compact={y} />
        <div className="flex rounded-md border border-line p-0.5" role="tablist" aria-label={msg("Workspace view")}>
          <button
            role="tab"
            aria-selected={view === `story`}
            onClick={() => setView(`story`)}
            className={cn(
              `flex items-center gap-1 rounded px-2 py-0.5 text-xs`,
              view === `story` ? `bg-panel-2 text-fg` : `text-muted`,
            )}
          >
            <Icon.MessageSquareText className="size-3.5" />{" "}
            {y ? <span className="sr-only">{msg("Story")}</span> : msg("Story")}
          </button>
          <button
            role="tab"
            aria-selected={view === `journal`}
            onClick={() => setView(`journal`)}
            className={cn(
              `flex items-center gap-1 rounded px-2 py-0.5 text-xs`,
              view === `journal` ? `bg-panel-2 text-fg` : `text-muted`,
            )}
          >
            <Icon.BookBookmark className="size-3.5" />{" "}
            {y ? <span className="sr-only">{msg("Journal & Memory")}</span> : msg("Journal & Memory")}
            {reviewCount > 0 && <Badge tone="accent">{reviewCount}</Badge>}
          </button>
        </div>
        <IconButton
          label={rightOpen ? msg("Hide status panel") : msg("Show status panel")}
          active={rightOpen}
          onClick={() => setRightOpen(!rightOpen)}
        >
          <Icon.PanelRight className="size-4" />
        </IconButton>
      </div>
    </header>
  );
}

// v0.6 (test report "30 tours", B11): inside the "⋯" menu (narrow window) these switches were popovers inside a
// popover: a click in the inner one counted as a click outside the menu, so the menu closed under it and the inner
// panel was left at the top-left corner of the screen, out of reach. Inside the menu they now open in place.
// StoryCore mobile (Phase 2): the play screen's only top bar on a phone. The app shell's bar is hidden there (App.jsx);
// ☰ opens the library, the title renames the story, then Codex, Journal, Status panel and the "⋯" menu (switches,
// notes, savepoints, context, help). Big touch targets, nothing behind a mouse hover.
function PhoneStoryHeader({
  story,
  branches,
  view,
  setView,
  rightOpen,
  setRightOpen,
  reviewCount,
  generating,
  onOpen,
  title,
  setTitle,
  editing,
  setEditing,
  saveTitle,
}) {
  let journal = view === `journal`;
  return (
    <header className="flex h-12 shrink-0 items-center gap-0.5 border-b border-line px-1">
      <IconButton label={msg("Open library")} onClick={openLibrary} className="size-10">
        <Icon.Menu className="size-5" />
      </IconButton>
      {editing ? (
        <form
          className="min-w-0 flex-1"
          onSubmit={(e) => {
            (e.preventDefault(), saveTitle(), setEditing(false));
          }}
        >
          <Input
            autoFocus
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            onBlur={() => setEditing(false)}
            className="h-8 w-full"
            aria-label={msg("Story title")}
          />
        </form>
      ) : (
        <button
          onClick={() => setEditing(true)}
          className="min-w-0 flex-1 truncate rounded px-1 py-1 text-left text-[15px] font-semibold"
          title={msg("Rename story")}
        >
          {story.title}
        </button>
      )}
      <BranchMenu story={story} branches={branches} disabled={generating} />
      <UsageMeter storyId={story.id} refreshKey={`${generating ? 1 : 0}:${story.updated_at ?? ``}`} />
      <CodexButton storyId={story.id} compact />
      <IconButton
        label={journal ? msg("Story") : msg("Journal & Memory")}
        active={journal}
        onClick={() => setView(journal ? `story` : `journal`)}
        className="relative size-10"
      >
        {journal ? <Icon.MessageSquareText className="size-5" /> : <Icon.BookBookmark className="size-5" />}
        {!journal && reviewCount > 0 && (
          <span className="absolute right-1 top-1 size-2 rounded-full bg-accent" aria-hidden />
        )}
      </IconButton>
      <IconButton
        label={rightOpen ? msg("Hide status panel") : msg("Show status panel")}
        active={rightOpen}
        onClick={() => setRightOpen(!rightOpen)}
        className="size-10"
      >
        <Icon.PanelRight className="size-5" />
      </IconButton>
      <MoreToolsMenu story={story} onOpen={onOpen} compact phone />
    </header>
  );
}

function MaybePopover({ inline, trigger, className, align, children }) {
  let [open, setOpen] = React.useState(false);
  if (!inline)
    return (
      <Popover>
        <PopoverTrigger asChild>{trigger}</PopoverTrigger>
        <PopoverContent className={className} align={align}>
          {children}
        </PopoverContent>
      </Popover>
    );
  return (
    <div className="w-full">
      {React.cloneElement(trigger, { onClick: () => setOpen(!open), "aria-expanded": open })}
      {open && (
        <div className={cn(`mt-1 w-full rounded border border-line bg-panel-2/40 p-1`, className.replace(/\bw-\d+\b/g, ``))}>
          {children}
        </div>
      )}
    </div>
  );
}

function MoreToolsMenu({ story, onOpen, compact, phone = false }) {
  let [r, i] = React.useState(false),
    a = `flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-xs text-muted hover:bg-panel-2 hover:text-fg`,
    o = (e) => {
      (i(false), onOpen(e));
    };
  return (
    <Popover open={r} onOpenChange={i}>
      <PopoverTrigger asChild>
        <IconButton label={msg("More story tools")} className={phone ? `size-10` : undefined}>
          <Icon.Ellipsis className={phone ? `size-5` : `size-4`} />
        </IconButton>
      </PopoverTrigger>
      <PopoverContent className={cn(`p-1`, compact ? `max-h-[80vh] w-80 overflow-y-auto` : `w-60`)} align="end">
        {compact && (
          <div className="mb-1 flex flex-col items-start gap-0.5 border-b border-line pb-1">
            <AvatarSwitch story={story} inline />
            <ModelSwitch story={story} inline />
            <StoryOptions story={story} inline />
          </div>
        )}
        <button className={a} onClick={() => o(`notes`)}>
          <Icon.NotebookPen className="size-3.5" /> {msg("User notes")}
        </button>
        <button className={a} onClick={() => o(`savepoints`)}>
          <Icon.Save className="size-3.5" /> {msg("Savepoints")}
        </button>
        {phone && (
          <>
            <button className={a} onClick={() => o(`context`)}>
              <Icon.Gauge className="size-3.5" /> {msg("Context sent to the model")}
            </button>
            <button
              className={a}
              onClick={() => {
                (i(false), openHelp());
              }}
            >
              <Icon.CircleQuestionMark className="size-3.5" /> {msg("Help and tour")}
            </button>
          </>
        )}
      </PopoverContent>
    </Popover>
  );
}

function SaveStatus() {
  let isMutating = useIsMutating(),
    mutationState = useMutationState({
      select: (e) => e.state.status,
    }),
    n = mutationState[mutationState.length - 1];
  return isMutating > 0 ? (
    <span className="flex items-center gap-1 px-1 text-[11px] text-muted" role="status">
      <Icon.LoaderCircle className="size-3 animate-spin" /> {msg("Saving")}
    </span>
  ) : n === `error` ? (
    <span className="flex items-center gap-1 px-1 text-[11px] text-danger" role="status">
      <Icon.CircleAlert className="size-3" /> {msg("Save failed")}
    </span>
  ) : null;
}

function BranchMenu({ story, branches, disabled }) {
  let invalidateStory = useInvalidateStory(),
    { toast, confirm } = useUi(),
    [o, s] = React.useState(false),
    c = branches.find((e) => e.active),
    l = branches.filter((e) => o || !e.archived || e.active);
  return branches.length <= 1 && !branches[0]?.archived ? (
    <span className="hidden items-center gap-1 text-[11px] text-faint lg:flex">
      <Icon.GitBranch className="size-3" /> {c?.label ?? msg("Main")}
    </span>
  ) : (
    <Popover>
      <PopoverTrigger asChild>
        <button
          className="flex items-center gap-1 rounded px-1.5 py-1 text-xs text-muted hover:bg-panel-2"
          disabled={disabled}
        >
          <Icon.GitBranch className="size-3.5" /> <span className="max-w-32 truncate">{c?.label}</span>{" "}
          <Icon.ChevronDown className="size-3" />
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-80 p-1" align="start">
        {l.map((t) => (
          <div
            className={cn(`group flex items-center gap-2 rounded px-2 py-1.5 text-xs`, t.active && `bg-panel-2`)}
            key={t.id}
          >
            <button
              className="min-w-0 flex-1 text-left"
              onClick={async () => {
                try {
                  (await apiPost(`/stories/${story.id}/branches/${t.id}/activate`), invalidateStory(story.id));
                } catch (e) {
                  toast(errorMessage(e), `danger`);
                }
              }}
            >
              <span className="block truncate font-medium">
                {t.label} {t.archived && <Badge>{msg("archived")}</Badge>}
              </span>
              <span className="block truncate text-faint">
                #{t.head_seq}
                {" · "}
                {t.head_preview || `empty`}
              </span>
            </button>
            {!t.active && !t.archived && (
              <button
                className="text-faint opacity-0 hover:text-danger group-hover:opacity-100"
                onClick={async () => {
                  if (
                    await confirm({
                      title: msg("Archive branch “{{v0}}”?", {
                        v0: t.label,
                      }),
                      body: msg(
                        "Archived branches stay in the database (a recovery savepoint is made) and can be reopened from this list.",
                      ),
                      danger: true,
                      confirmLabel: msg("Archive branch"),
                    })
                  )
                    try {
                      (await apiDelete(`/stories/${story.id}/branches/${t.id}?confirm=true`),
                        invalidateStory(story.id));
                    } catch (e) {
                      toast(errorMessage(e), `danger`);
                    }
                }}
              >
                {msg("archive")}
              </button>
            )}
          </div>
        ))}
        <label className="mt-1 flex items-center gap-2 border-t border-line px-2 pt-1.5 text-[11px] text-faint">
          <input type="checkbox" checked={o} onChange={(e) => s(e.target.checked)} /> {msg("Show archived branches")}
        </label>
      </PopoverContent>
    </Popover>
  );
}

function AvatarSwitch({ story, inline = false }) {
  let avatars = useAvatars(),
    invalidateStory = useInvalidateStory(),
    { confirm, toast } = useUi(),
    a = async (t) => {
      if (!(
        (story.message_count ?? 0) > 0 &&
        !(await confirm({
          title: msg("Switch the protagonist?"),
          body: msg(
            "The story's transcript, relationships and journal were built around the current avatar. Switching can break continuity (NPCs may 'know' the wrong person). An automatic savepoint is created first.",
          ),
          confirmLabel: msg("Switch avatar"),
          danger: true,
        }))
      ))
        try {
          (await apiPost(`/stories/${story.id}/avatar`, {
            avatar_id: t,
            confirm: true,
          }),
            invalidateStory(story.id),
            toast(msg("Avatar switched")));
        } catch (e) {
          toast(errorMessage(e), `danger`);
        }
    };
  return (
    <MaybePopover inline={inline} align="start" className="w-64 p-1" trigger={
        <button
          className="flex items-center gap-1.5 rounded px-1.5 py-1 text-xs text-muted hover:bg-panel-2"
          title={msg("Active avatar")}
        >
          <UploadedImage path={story.avatar_portrait} name={story.avatar_name ?? `?`} className="size-5 rounded-full" />
          <span className="max-w-24 truncate">{story.avatar_name ?? msg("No avatar")}</span>
          <Icon.ChevronDown className="size-3" />
        </button>
      }>
        {avatars.data?.map((t) => (
          <button
            onClick={() => t.id !== story.active_avatar_id && a(t.id)}
            className={cn(
              `flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-xs hover:bg-panel-2`,
              t.id === story.active_avatar_id && `bg-panel-2`,
            )}
            key={t.id}
          >
            <UploadedImage path={t.portrait_path} name={t.name} className="size-6 rounded-full" />
            <span className="flex-1 truncate">{t.name}</span>
            {t.id === story.active_avatar_id && <Icon.Check className="size-3.5 text-accent" />}
          </button>
        ))}
        <div className="mt-1 border-t border-line pt-1">
          <button
            onClick={() => navigate(`/avatars`)}
            className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-xs text-accent hover:bg-panel-2"
          >
            <Icon.UserRound className="size-3.5" /> {msg("Manage avatars")}
          </button>
        </div>
      </MaybePopover>
  );
}

function ModelSwitch({ story, inline = false }) {
  let t = useProviders(),
    invalidateStory = useInvalidateStory(),
    [r, i] = React.useState({}),
    a = story.settings_json.model_profile_id,
    o = a ?? t.data?.default_model_profile_id ?? null,
    s = t.data?.profiles.find((e) => e.id === o),
    c = t.data?.providers.find((e) => e.id === s?.provider_id),
    l = c ? r[c.id] : undefined,
    u = !!c?.is_cloud || (!!s && isCloudModelId(s.model_id)),
    d = async (t) => {
      (await apiPatch(`/stories/${story.id}`, {
        settings: {
          model_profile_id: t,
        },
      }),
        invalidateStory(story.id));
    },
    f = async (e) => {
      i((t) => ({
        ...t,
        [e]: `pending`,
      }));
      let t = await apiPost(`/providers/${e}/test`, {
        model_id: s?.model_id,
        record: true,
      }).catch((e) => ({
        ok: false,
        message: errorMessage(e),
      }));
      i((n) => ({
        ...n,
        [e]: t,
      }));
    };
  return (
    <MaybePopover inline={inline} align="start" className="w-80 p-1" trigger={
        <button
          className="flex items-center gap-1.5 rounded px-1.5 py-1 text-xs text-muted hover:bg-panel-2"
          title={msg("Provider and model")}
        >
          <span
            className={cn(
              `size-1.5 rounded-full`,
              l === `pending` ? `bg-warn` : l ? (l.ok ? `bg-ok` : `bg-danger`) : `bg-faint`,
            )}
            aria-hidden
          />
          {u ? <Icon.Cloud className="size-3.5" /> : <Icon.HardDrive className="size-3.5" />}
          <span className="max-w-36 truncate">{s ? s.display_name : msg("No model")}</span>
          <Icon.ChevronDown className="size-3" />
        </button>
      }>
        <p className="px-2 py-1 text-[11px] text-faint">
          {u
            ? msg("Remote model — story content is sent to the provider.")
            : msg("Local only — nothing leaves your computer.")}
        </p>
        {l && l !== `pending` && (
          <p className={cn(`px-2 pb-1 text-[11px]`, l.ok ? `text-ok` : `text-danger`)}>{l.message}</p>
        )}
        <button
          onClick={() => d(null)}
          className={cn(
            `flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-xs hover:bg-panel-2`,
            !a && `bg-panel-2`,
          )}
        >
          {msg("Use global default")}
          {!a && <Icon.Check className="ml-auto size-3.5 text-accent" />}
        </button>
        {t.data?.providers.map((e) => {
          let n = t.data.profiles.filter((t) => t.provider_id === e.id);
          return n.length ? (
            <div className="mt-1" key={e.id}>
              <p className="flex items-center gap-1 px-2 py-0.5 text-[10px] uppercase tracking-wider text-faint">
                {e.display_name}{" "}
                {e.is_cloud ? <Badge tone="warn">{msg("cloud")}</Badge> : <Badge tone="ok">{msg("local")}</Badge>}
              </p>
              {n.map((e) => (
                <button
                  onClick={() => d(e.id)}
                  className={cn(
                    `flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-xs hover:bg-panel-2`,
                    a === e.id && `bg-panel-2`,
                  )}
                  key={e.id}
                >
                  <span className="truncate">{e.display_name}</span>
                  {e.id === t.data?.default_model_profile_id && <Badge>{msg("default")}</Badge>}
                  {a === e.id && <Icon.Check className="ml-auto size-3.5 text-accent" />}
                </button>
              ))}
            </div>
          ) : null;
        })}
        <div className="mt-1 flex gap-1 border-t border-line pt-1">
          {c && (
            <Button size="sm" variant="ghost" onClick={() => f(c.id)}>
              {msg("Test connection")}
            </Button>
          )}
          <Button size="sm" variant="ghost" className="ml-auto" onClick={() => navigate(`/settings/providers`)}>
            {msg("Manage providers")}
          </Button>
        </div>
      </MaybePopover>
  );
}

function StoryOptions({ story, inline = false }) {
  let settings = useSettings(),
    queryClient = useQueryClient(),
    r = story.settings_json,
    i = async (t, r) => {
      (await apiPatch(`/stories/${story.id}`, {
        settings: {
          [t]: r === `` ? null : r,
        },
      }),
        queryClient.invalidateQueries({
          queryKey: queryKeys.story(story.id),
        }),
        queryClient.invalidateQueries({
          queryKey: queryKeys.context(story.id),
        }));
    },
    presets = settings.data?.narration_presets ?? [];
  return (
    <MaybePopover inline={inline} align="start" className="w-80 space-y-2.5" trigger={
        <button
          className="flex items-center gap-1 rounded px-1.5 py-1 text-xs text-muted hover:bg-panel-2"
          title={msg("Story mode and generation options")}
        >
          <Icon.SlidersHorizontal className="size-3.5" />{" "}
          {presetName(presets.find((preset) => preset.id === (r.preset_id ?? `balanced`))) || msg("Balanced")}
          <Icon.ChevronDown className="size-3" />
        </button>
      }>
        <label className="block text-xs text-muted">
          {msg("Narration preset")}
          <Select value={String(r.preset_id ?? `balanced`)} onChange={(e) => i(`preset_id`, e.target.value)}>
            {presets.map((preset) => (
              <option value={preset.id} key={preset.id}>
                {presetName(preset)}
              </option>
            ))}
          </Select>
        </label>
        <label className="block text-xs text-muted">
          {msg("Story language")}
          <Select value={String(r.narration_language ?? ``)} onChange={(e) => i(`narration_language`, e.target.value)}>
            <option value="">
              {msg("App setting")} ({settings.data?.narration_language === `fr` ? msg("French") : msg("English")})
            </option>
            <option value="en">{msg("English")}</option>
            <option value="fr">{msg("French")}</option>
          </Select>
        </label>
        <label className="block text-xs text-muted">
          {msg("Output length")}
          <Select value={String(r.output_length ?? ``)} onChange={(e) => i(`output_length`, e.target.value)}>
            <option value="">{msg("Model default")}</option>
            <option value="short (1–2 paragraphs)">{msg("Short (1–2 paragraphs)")}</option>
            <option value="medium (3–4 paragraphs)">{msg("Medium (3–4 paragraphs)")}</option>
            <option value="long (5–7 paragraphs)">{msg("Long (5–7 paragraphs)")}</option>
          </Select>
        </label>
        <label className="block text-xs text-muted">
          {msg("Max output tokens")}
          <Input
            type="number"
            min={16}
            max={32e3}
            defaultValue={String(r.max_tokens ?? ``)}
            onBlur={(e) => i(`max_tokens`, e.target.value ? Number(e.target.value) : null)}
            placeholder={msg("the model's setting")}
          />
          <span className="mt-0.5 block text-[10px] text-faint">
            {msg("A ceiling for hosted models, not a target. Empty uses the model's setting.")}
          </span>
        </label>
        <label className="block text-xs text-muted">
          {msg("Relationship progression")}
          <Select
            value={String(r.relationship_difficulty ?? `normal`)}
            onChange={(e) => i(`relationship_difficulty`, e.target.value === `normal` ? null : e.target.value)}
          >
            <option value="relaxed">{msg("Relaxed — faster warmth, small slips forgiven")}</option>
            <option value="normal">{msg("Normal — balanced")}</option>
            <option value="strict">{msg("Strict — slower bonds, higher stages")}</option>
          </Select>
          <span className="mt-0.5 block text-[10px] text-faint">
            {msg("Applies to new changes only; existing values stay. Serious betrayals count fully in every mode.")}
          </span>
        </label>
        <label className="block text-xs text-muted">
          {msg("Narrative presentation")}
          <Select
            value={String(r.narrative_presentation ?? `classic`)}
            onChange={(e) => i(`narrative_presentation`, e.target.value === `classic` ? null : e.target.value)}
          >
            <option value="classic">{msg("Classic — the reply follows your whole turn")}</option>
            <option value="immersive">{msg("Immersive dialogue — reactions between your quoted lines")}</option>
          </Select>
          <span className="mt-0.5 block text-[10px] text-faint">
            {msg(
              'Immersive applies when your turn has two or more quoted lines (« », “ ” or " "). Your words are never changed; switching back loses nothing.',
            )}
          </span>
        </label>
        <label className="block text-xs text-muted">
          {msg("Tone")}
          <Input
            defaultValue={String(r.tone ?? ``)}
            onBlur={(e) => i(`tone`, e.target.value)}
            placeholder={msg("e.g. hopeful, tense, comedic")}
          />
        </label>
        <label className="block text-xs text-muted">
          {msg("Player-agency note (optional)")}
          <Input
            defaultValue={String(r.agency_policy ?? ``)}
            onBlur={(e) => i(`agency_policy`, e.target.value)}
            placeholder={msg("The built-in rules always apply")}
          />
        </label>
        <label className="block text-xs text-muted">
          {msg("Context budget for this story (tokens)")}
          <Input
            type="number"
            defaultValue={String(r.context_budget_tokens ?? ``)}
            onBlur={(e) => i(`context_budget_tokens`, e.target.value ? Number(e.target.value) : null)}
            placeholder={msg("global default ({{v0}})", {
              v0: settings.data?.context_budget_tokens ?? 8e3,
            })}
          />
        </label>
        <p className="text-[11px] text-faint">
          {msg("Temperature and other model parameters are set per model in Settings → Providers.")}
        </p>
        <Button size="sm" variant="ghost" onClick={() => navigate(`/settings/generation`)}>
          {msg("Edit presets")}
        </Button>
      </MaybePopover>
  );
}
