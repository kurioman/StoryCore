// Reconstructed from the StoryCore v1.7.0 compiled bundle (see DEVONLY/13_FRONTEND_SOURCE.md).
import { useStories, queryKeys } from "@/api/queries";
import * as React from "react";
import * as Icon from "lucide-react";
import { errorMessage, apiPatch, apiPost, apiDelete, apiUpload } from "@/api/legacy";
import { useQueryClient, useMutation } from "@tanstack/react-query";
import { msg, msgKey } from "@/i18n";
import {
  Badge,
  Button,
  Callout,
  IconButton,
  Input,
  Modal,
  Popover,
  PopoverContent,
  PopoverTrigger,
  useUi,
} from "@/components/ui";
import { cn, timeAgo } from "@/lib/util";
import { navigate } from "@/lib/router";

export function Logo({ small }) {
  return (
    <svg viewBox="0 0 32 32" className={small ? `size-5` : `size-6`} aria-hidden>
      <path
        d="M16 2.5 L19.2 12.8 L29.5 16 L19.2 19.2 L16 29.5 L12.8 19.2 L2.5 16 L12.8 12.8 Z"
        fill="var(--c-accent)"
      />

      <circle cx="16" cy="16" r="2.4" fill="var(--c-bg)" />
    </svg>
  );
}

export function Sidebar({ activeStoryId, path, collapsed, onToggle, onHelp }) {
  let stories = useStories(),
    [o, s] = React.useState(``),
    [c, l] = React.useState(`active`),
    [u, d] = React.useState(false),
    f = React.useMemo(() => {
      let e = o.toLowerCase();
      return (stories.data ?? []).filter(
        (t) =>
          t.status === c && (!e || t.title.toLowerCase().includes(e) || (t.world_name ?? ``).toLowerCase().includes(e)),
      );
    }, [stories.data, o, c]),
    p = React.useMemo(() => {
      let e = {
        active: 0,
        archived: 0,
        template: 0,
      };
      for (let t of stories.data ?? []) e[t.status] = (e[t.status] ?? 0) + 1;
      return e;
    }, [stories.data]),
    g = [
      {
        to: `/avatars`,
        label: msg("Avatars"),
        icon: Icon.UserRound,
      },
      {
        to: `/lore`,
        label: msg("Lore library"),
        icon: Icon.BookOpen,
      },
      {
        to: `/portraits`,
        label: msg("Portraits"),
        icon: Icon.Images,
      },
      {
        to: `/music`,
        label: msg("Music"),
        icon: Icon.Music,
      },
      {
        to: `/commands`,
        label: msg("Commands"),
        icon: Icon.SquareSlash,
      },
      {
        to: `/settings`,
        label: msg("Settings"),
        icon: Icon.Settings,
      },
    ];

  return collapsed ? (
    <aside className="flex h-full w-12 shrink-0 flex-col items-center gap-1 border-r border-line bg-panel py-2">
      <button onClick={() => navigate(`/`)} aria-label={msg("Home")} className="mb-1 p-1">
        <Logo small />
      </button>
      <IconButton label={msg("Expand library")} onClick={onToggle}>
        <Icon.ChevronsRight className="size-4" />
      </IconButton>
      <IconButton label={msg("New story")} onClick={() => navigate(`/new`)}>
        <Icon.Plus className="size-4" />
      </IconButton>
      <div className="my-1 h-px w-6 bg-line" />
      {g.map((e) => (
        <IconButton label={e.label} active={path.startsWith(e.to)} onClick={() => navigate(e.to)} key={e.to}>
          <e.icon className="size-4" />
        </IconButton>
      ))}
      <IconButton label={msg("Help and tour")} onClick={onHelp}>
        <Icon.CircleQuestionMark className="size-4" />
      </IconButton>
    </aside>
  ) : (
    <aside className="flex h-full w-72 shrink-0 flex-col border-r border-line bg-panel">
      <div className="flex h-12 items-center gap-2 px-3">
        <button onClick={() => navigate(`/`)} className="flex items-center gap-2" aria-label={msg("Home")}>
          <Logo />
          <span className="sc-brand text-[16px] text-accent">{msg("StoryCore")}</span>
        </button>
        <IconButton label={msg("Collapse library")} className="ml-auto" onClick={onToggle}>
          <Icon.ChevronsLeft className="size-4" />
        </IconButton>
      </div>
      <div className="flex gap-1.5 px-3 pb-2">
        <Button variant="primary" className="flex-1" onClick={() => navigate(`/new`)}>
          <Icon.Plus className="size-4" /> {msg("New story")}
        </Button>
        <IconButton label={msg("Import story package")} className="size-8.5 border border-line" onClick={() => d(true)}>
          <Icon.Upload className="size-4" />
        </IconButton>
      </div>
      <div className="px-3 pb-2">
        <div className="relative">
          <Icon.Search className="absolute left-2 top-2.5 size-3.5 text-faint" aria-hidden />
          <Input
            value={o}
            onChange={(e) => s(e.target.value)}
            placeholder={msg("Search stories")}
            className="pl-7"
            aria-label={msg("Search stories")}
          />
        </div>
      </div>
      <div className="flex gap-1 px-3 pb-1" role="tablist" aria-label={msg("Story groups")}>
        {[`active`, `archived`, `template`].map((e) => (
          <button
            role="tab"
            aria-selected={c === e}
            onClick={() => l(e)}
            className={cn(
              `rounded px-2 py-0.5 text-xs capitalize`,
              c === e ? `bg-panel-2 text-fg` : `text-faint hover:text-muted`,
            )}
            key={e}
          >
            {e === `template` ? msg("Templates") : e === `active` ? msg("Active") : msg("Archived")}{" "}
            {p[e] ? <span className="text-faint">{p[e]}</span> : null}
          </button>
        ))}
      </div>
      <nav className="min-h-0 flex-1 overflow-y-auto px-2 py-1" aria-label={msg("Stories")}>
        {stories.isLoading && <p className="px-2 py-3 text-xs text-faint">{msg("Loading…")}</p>}
        {stories.isError && <p className="px-2 py-3 text-xs text-danger">{errorMessage(stories.error)}</p>}
        {!stories.isLoading && f.length === 0 && (
          <p className="px-2 py-3 text-xs text-faint">
            {o
              ? msg("No matching stories.")
              : c === `active`
                ? msg("No stories yet — create one to begin.")
                : msg("No {{v0}} stories.", {
                    v0: c,
                  })}
          </p>
        )}
        {f.map((t) => (
          <StoryRow s={t} active={t.id === activeStoryId} key={t.id} />
        ))}
      </nav>
      <div className="border-t border-line p-2">
        {g.map((e) => (
          <button
            onClick={() => navigate(e.to)}
            className={cn(
              `flex w-full items-center gap-2.5 rounded-md px-2 py-1.5 text-[13px] text-muted hover:bg-panel-2 hover:text-fg`,
              path.startsWith(e.to) && `bg-panel-2 text-fg`,
            )}
            key={e.to}
          >
            <e.icon className="size-4" /> {e.label}
          </button>
        ))}
        <button
          onClick={onHelp}
          className="flex w-full items-center gap-2.5 rounded-md px-2 py-1.5 text-[13px] text-muted hover:bg-panel-2 hover:text-fg"
        >
          <Icon.CircleQuestionMark className="size-4" /> {msg("Help")}
        </button>
      </div>
      <ImportStoryDialog open={u} onOpenChange={d} />
    </aside>
  );
}

function StoryRow({ s: e, active }) {
  let queryClient = useQueryClient(),
    { toast, confirm } = useUi(),
    [a, o] = React.useState(false),
    [s, c] = React.useState(e.title),
    l = () =>
      queryClient.invalidateQueries({
        queryKey: queryKeys.stories,
      }),
    mutation = useMutation({
      mutationFn: async (t) => {
        if (t === `rename`)
          return apiPatch(`/stories/${e.id}`, {
            title: s,
          });
        if (t === `archive`)
          return apiPatch(`/stories/${e.id}`, {
            status: e.status === `archived` ? `active` : `archived`,
          });
        if (t === `template`)
          return apiPatch(`/stories/${e.id}`, {
            status: e.status === `template` ? `active` : `template`,
          });
        if (t === `duplicate`) return apiPost(`/stories/${e.id}/duplicate`);
        if (t === `delete`) return apiDelete(`/stories/${e.id}?confirm=true`);
      },
      onSuccess: (i, a) => {
        (l(),
          queryClient.invalidateQueries({
            queryKey: queryKeys.story(e.id),
          }),
          a === `duplicate` && toast(msg("Story duplicated")),
          a === `delete` &&
            (toast(msg("Story deleted. A recovery package was saved in data/backups/deleted_stories.")),
            active && navigate(`/library`)),
          a === `archive` && toast(e.status === `archived` ? msg("Story restored", {}) : msg("Story archived", {})));
      },
      onError: (e) => toast(errorMessage(e), `danger`),
    });
  return (
    <div className={cn(`group relative mb-0.5 rounded-md`, active ? `bg-panel-2` : `hover:bg-panel-2/60`)}>
      {a ? (
        <form
          className="p-1.5"
          onSubmit={(e) => {
            (e.preventDefault(), mutation.mutate(`rename`), o(false));
          }}
        >
          <Input
            autoFocus
            value={s}
            onChange={(e) => c(e.target.value)}
            onBlur={() => o(false)}
            aria-label={msg("Story title")}
          />
        </form>
      ) : (
        <button
          onClick={() => navigate(`/story/${e.id}`)}
          className="block w-full px-2.5 py-2 pr-8 text-left"
          aria-current={active ? `page` : undefined}
        >
          <div className="truncate text-[13px] font-medium">{e.title}</div>
          <div className="mt-0.5 flex items-center gap-1.5 text-[11px] text-faint">
            <span>{timeAgo(e.last_activity)}</span>
            {e.world_name && (
              <>
                <span>·</span>
                <span className="truncate">{e.world_name}</span>
              </>
            )}
            {e.message_count ? (
              <span className="ml-auto">
                {e.message_count} {msg("msg")}
              </span>
            ) : null}
          </div>
        </button>
      )}
      {!a && (
        <Popover>
          <PopoverTrigger asChild>
            <IconButton
              label={msg("Actions for {{v0}}", {
                v0: e.title,
              })}
              className="absolute right-1 top-1.5 opacity-0 group-hover:opacity-100 focus:opacity-100 data-[state=open]:opacity-100"
            >
              <Icon.Ellipsis className="size-4" />
            </IconButton>
          </PopoverTrigger>
          <PopoverContent align="end" className="w-44 p-1">
            <MenuItem icon={Icon.Pencil} label={msg("Rename")} onClick={() => o(true)} />
            <MenuItem icon={Icon.Copy} label={msg("Duplicate")} onClick={() => mutation.mutate(`duplicate`)} />
            <MenuItem
              icon={Icon.Download}
              label={msg("Export package")}
              onClick={() => (window.location.href = `/api/stories/${e.id}/export`)}
            />

            <MenuItem
              icon={e.status === `archived` ? Icon.ArchiveArrowUp : Icon.Archive}
              label={e.status === `archived` ? msg("Unarchive") : msg("Archive")}
              onClick={() => mutation.mutate(`archive`)}
            />

            <MenuItem
              icon={Icon.BookOpen}
              label={e.status === `template` ? msg("Unmark template") : msg("Mark as template")}
              onClick={() => mutation.mutate(`template`)}
            />

            <div className="my-1 h-px bg-line" />
            <MenuItem
              icon={Icon.Trash}
              danger
              label={msg("Delete…")}
              onClick={async () => {
                (await confirm({
                  title: msg("Delete “{{v0}}”?", {
                    v0: e.title,
                  }),
                  body: msg(
                    "The story, its branches, journal and savepoints are removed. Avatars, global notes, providers and lore are not affected. A recovery package is saved in the backups folder first.",
                  ),
                  confirmLabel: msg("Delete story"),
                  danger: true,
                })) && mutation.mutate(`delete`);
              }}
            />
          </PopoverContent>
        </Popover>
      )}
    </div>
  );
}

function MenuItem({ icon: CompE, label, onClick, danger, disabled }) {
  return (
    <button
      disabled={disabled}
      onClick={onClick}
      className={cn(
        `flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-[13px] hover:bg-panel-2 disabled:opacity-40`,
        danger ? `text-danger` : `text-fg`,
      )}
    >
      <CompE className="size-3.5" /> {label}
    </button>
  );
}

function ImportStoryDialog({ open, onOpenChange }) {
  let n = React.useRef(null),
    queryClient = useQueryClient(),
    { toast } = useUi(),
    [a, o] = React.useState(null),
    [s, c] = React.useState(false),
    [l, u] = React.useState(null),
    d = async (e) => {
      (c(true), u(null));
      try {
        let t = new FormData();
        (t.append(`file`, e), o(await apiUpload(`/import/story/preview`, t)));
      } catch (e) {
        u(errorMessage(e));
      } finally {
        c(false);
      }
    };
  return (
    <Modal
      open={open}
      onOpenChange={(e) => {
        (onOpenChange(e), e || o(null));
      }}
      title={msg("Import a story package")}
      description={msg("Packages (.zip) exported from StoryCore or Lumencia Story Desk. Imports always create a copy.")}
      footer={
        a ? (
          <>
            <Button variant="ghost" onClick={() => o(null)}>
              {msg("Choose another file")}
            </Button>
            <Button
              variant="primary"
              loading={s}
              onClick={async () => {
                if (a) {
                  c(true);
                  try {
                    let e = await apiPost(`/import/story/confirm`, {
                      token: a.token,
                    });
                    (queryClient.invalidateQueries({
                      queryKey: queryKeys.stories,
                    }),
                      toast(msg("Story imported as a new copy")),
                      onOpenChange(false),
                      o(null),
                      navigate(`/story/${e.story_id}`));
                  } catch (e) {
                    u(errorMessage(e));
                  } finally {
                    c(false);
                  }
                }
              }}
            >
              {msg("Import as new story")}
            </Button>
          </>
        ) : undefined
      }
    >
      <input
        ref={n}
        type="file"
        accept=".zip"
        className="hidden"
        onChange={(e) => e.target.files?.[0] && d(e.target.files[0])}
      />

      {!a && (
        <Button onClick={() => n.current?.click()} loading={s}>
          <Icon.Upload className="size-4" /> {msg("Choose package…")}
        </Button>
      )}
      {l && (
        <Callout tone="danger" className="mt-3">
          {l}
        </Callout>
      )}
      {a && (
        <div className="space-y-3 text-sm">
          <p className="font-medium">{a.report.title}</p>
          <div className="flex flex-wrap gap-1.5">
            {Object.entries(a.report.counts ?? {}).map(([e, t]) => (
              <Badge key={e}>
                {msgKey(e)}
                {": "}
                {t}
              </Badge>
            ))}
          </div>
          {a.report.world && (
            <Callout tone={a.report.world.found ? `ok` : `warn`}>
              {msg("World “")}
              {a.report.world.name}
              {"” "}
              {a.report.world.found
                ? msg("is available locally.")
                : msg("is not imported here; the story will open without lore until you import that world.")}
            </Callout>
          )}
          {a.report.missing_assets.length > 0 && (
            <Callout tone="warn">
              {msg("Missing assets in package:")} {a.report.missing_assets.join(`, `)}
            </Callout>
          )}
          {a.report.unresolved_count > 0 && (
            <Callout tone="warn">
              {a.report.unresolved_count}{" "}
              {msg("record reference(s) point outside the package (they will be kept but cannot be followed).")}
            </Callout>
          )}
          <p className="text-xs text-muted">{a.report.policy}</p>
        </div>
      )}
    </Modal>
  );
}
