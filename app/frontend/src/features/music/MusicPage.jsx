// Music library page (v0.5) at #/music: the app's one music library (<project>/Music). Add .mp3 files, listen,
// rename, tag (predefined tags by family, or your own), delete. Lore packs pick from this library by tag.
import * as React from "react";
import * as Icon from "lucide-react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiDelete, apiGet, apiPatch, apiUpload, errorMessage } from "@/api/legacy";
import { msg } from "@/i18n";
import { Input, Popover, PopoverContent, PopoverTrigger, Spinner, useUi } from "@/components/ui";
import { cn } from "@/lib/util";
import { groupLabel, tagLabel, useMusicTags } from "@/features/music/tags";

export function MusicPage() {
  let tracks = useQuery({ queryKey: [`music-tracks`], queryFn: () => apiGet(`/music/tracks`) }),
    tags = useMusicTags(),
    queryClient = useQueryClient(),
    { toast, confirm } = useUi(),
    fileInput = React.useRef(null),
    audio = React.useRef(null),
    [playing, setPlaying] = React.useState(null),
    [uploading, setUploading] = React.useState(false),
    [filter, setFilter] = React.useState(``),
    [search, setSearch] = React.useState(``),
    [dragging, setDragging] = React.useState(false),
    refresh = () => queryClient.invalidateQueries({ queryKey: [`music-tracks`] });

  React.useEffect(() => () => audio.current?.pause(), []);

  async function upload(files) {
    let list = [...files].filter(Boolean);
    if (!list.length) return;
    let fd = new FormData();
    list.forEach((f) => fd.append(`files`, f));
    setUploading(true);
    try {
      let r = await apiUpload(`/music/tracks`, fd);
      toast(msg("{{v0}} track(s) added. Add tags so stories can use them.", { v0: r.added.length }));
      r.errors?.forEach((e) => toast(e, `danger`));
      refresh();
    } catch (e) {
      toast(errorMessage(e), `danger`);
    } finally {
      setUploading(false);
    }
  }

  async function save(id, changes) {
    try {
      await apiPatch(`/music/tracks/${id}`, changes);
      refresh();
    } catch (e) {
      toast(errorMessage(e), `danger`);
    }
  }

  async function remove(t) {
    if (
      !(await confirm({
        title: msg("Delete \"{{v0}}\"?", { v0: t.title }),
        body: msg("The track is removed from the library and its file is deleted from the Music folder."),
        danger: true,
        confirmLabel: msg("Delete"),
      }))
    )
      return;
    if (playing === t.id) toggle(t);
    try {
      await apiDelete(`/music/tracks/${t.id}`);
      refresh();
    } catch (e) {
      toast(errorMessage(e), `danger`);
    }
  }

  function toggle(t) {
    if (!audio.current) audio.current = new Audio();
    if (playing === t.id) {
      audio.current.pause();
      setPlaying(null);
      return;
    }
    audio.current.src = `/api/music/tracks/${t.id}/file`;
    audio.current.volume = 0.6;
    audio.current.play().catch(() => {});
    audio.current.onended = () => setPlaying(null);
    setPlaying(t.id);
  }

  let all = tracks.data?.tracks ?? [],
    shown = all.filter(
      (t) =>
        (!filter || (filter === `__untagged` ? !t.tags.length : t.tags.includes(filter))) &&
        (!search || t.title.toLowerCase().includes(search.toLowerCase())),
    ),
    usedTags = [...new Set(all.flatMap((t) => t.tags))].sort((a, b) => tagLabel(tags.data, a).localeCompare(tagLabel(tags.data, b)));

  return (
    <div
      className="sc-lib h-full overflow-y-auto"
      onDragOver={(e) => {
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragging(false);
        upload(e.dataTransfer.files);
      }}
    >
      <div className="mx-auto max-w-5xl px-6 py-8">
        <header className="mb-2 flex flex-wrap items-center gap-3">
          <Icon.Music className="size-7 text-[#e2bd72]" />
          <h1 className="sc-brand text-3xl text-[#f3dca0]">{msg("Music")}</h1>
          <span className="sc-cx-count text-[#e2bd72]">{all.length}</span>
          <button className="sc-lib-cta ml-auto" onClick={() => fileInput.current?.click()} disabled={uploading}>
            {uploading ? <Icon.LoaderCircle className="size-4 animate-spin" /> : <Icon.Upload className="size-4" />}{" "}
            {msg("Add music")}
          </button>
          <input
            ref={fileInput}
            type="file"
            multiple
            accept=".mp3,.ogg,.m4a,.wav,audio/*"
            className="hidden"
            onChange={(e) => {
              upload(e.target.files);
              e.target.value = ``;
            }}
          />
        </header>
        <p className="mb-6 text-sm text-[#ece6d8b3]">
          {msg(
            "One music library for every story. Tag each track: during a story the music follows the scene's mood and place, using these tags. Lore packs can also pick tracks by tag. Prefer .mp3 files; you can drop them on this page.",
          )}
        </p>

        <div className={cn(`sc-mu-drop mb-6`, dragging && `sc-mu-drop-on`)}>
          <Icon.FileAudio className="size-5" /> {msg("Drop .mp3 files here to add them")}
        </div>

        {all.length > 0 && (
          <div className="mb-5 flex flex-wrap items-center gap-2">
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder={msg("Search a title")}
              className="w-56"
            />
            <button className={cn(`sc-mu-chip`, !filter && `sc-mu-chip-on`)} onClick={() => setFilter(``)}>
              {msg("All")}
            </button>
            <button className={cn(`sc-mu-chip`, filter === `__untagged` && `sc-mu-chip-on`)} onClick={() => setFilter(`__untagged`)}>
              {msg("Without tags")}
            </button>
            {usedTags.map((t) => (
              <button key={t} className={cn(`sc-mu-chip`, filter === t && `sc-mu-chip-on`)} onClick={() => setFilter(t)}>
                {tagLabel(tags.data, t)}
              </button>
            ))}
          </div>
        )}

        {tracks.isLoading && <Spinner />}
        {tracks.data && !all.length && (
          <p className="rounded-xl border border-dashed border-[#e2bd7240] p-8 text-center text-sm text-[#e2bd72aa]">
            {msg("No music yet. Add your first .mp3 files with the button above.")}
          </p>
        )}
        <div className="space-y-2">
          {shown.map((t) => (
            <TrackRow
              key={t.id}
              track={t}
              tags={tags.data}
              playing={playing === t.id}
              onToggle={() => toggle(t)}
              onSave={(c) => save(t.id, c)}
              onDelete={() => remove(t)}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

function TrackRow({ track, tags, playing, onToggle, onSave, onDelete }) {
  let [title, setTitle] = React.useState(track.title);
  React.useEffect(() => setTitle(track.title), [track.title]);
  return (
    <div className={cn(`sc-mu-row`, !track.available && `opacity-60`)}>
      <button
        className={cn(`sc-mu-play`, playing && `sc-mu-play-on`)}
        onClick={onToggle}
        disabled={!track.available}
        aria-label={playing ? msg("Pause") : msg("Listen")}
        title={playing ? msg("Pause") : msg("Listen")}
      >
        {playing ? <Icon.Pause className="size-4" /> : <Icon.Play className="size-4" />}
      </button>
      <div className="min-w-0 flex-1">
        <input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          onBlur={() => title.trim() && title !== track.title && onSave({ title })}
          onKeyDown={(e) => e.key === `Enter` && e.currentTarget.blur()}
          className="sc-mu-title"
          aria-label={msg("Title")}
        />
        <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
          {track.tags.map((id) => (
            <span key={id} className="sc-mu-tag">
              {tagLabel(tags, id)}
              <button
                onClick={() => onSave({ tags: track.tags.filter((x) => x !== id) })}
                aria-label={msg("Remove the tag {{v0}}", { v0: tagLabel(tags, id) })}
                className="opacity-60 hover:opacity-100"
              >
                <Icon.X className="size-3" />
              </button>
            </span>
          ))}
          <TagPicker tags={tags} current={track.tags} onAdd={(id) => onSave({ tags: [...track.tags, id] })} />
          {!track.available && <span className="text-xs text-danger">{msg("File missing")}</span>}
        </div>
      </div>
      <button className="sc-mu-del" onClick={onDelete} aria-label={msg("Delete")} title={msg("Delete")}>
        <Icon.Trash2 className="size-4" />
      </button>
    </div>
  );
}

function TagPicker({ tags, current, onAdd }) {
  let [open, setOpen] = React.useState(false),
    [custom, setCustom] = React.useState(``);
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button className="sc-mu-add">
          <Icon.Plus className="size-3" /> {msg("Tag")}
        </button>
      </PopoverTrigger>
      <PopoverContent align="start" className="sc-menu w-[min(560px,90vw)] p-3">
        <div className="max-h-[50vh] space-y-3 overflow-y-auto">
          {(tags?.groups ?? []).map((g) => (
            <div key={g.id}>
              <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-[#e2bd72b0]">{groupLabel(tags, g.id)}</p>
              <div className="flex flex-wrap gap-1.5">
                {tags.tags
                  .filter((t) => t.group === g.id)
                  .map((t) => (
                    <button
                      key={t.id}
                      disabled={current.includes(t.id)}
                      onClick={() => onAdd(t.id)}
                      className="sc-mu-chip disabled:opacity-35"
                    >
                      {tagLabel(tags, t.id)}
                    </button>
                  ))}
              </div>
            </div>
          ))}
        </div>
        <form
          className="mt-3 flex gap-2 border-t border-[#e2bd7226] pt-3"
          onSubmit={(e) => {
            e.preventDefault();
            if (custom.trim()) {
              onAdd(custom.trim());
              setCustom(``);
            }
          }}
        >
          <Input value={custom} onChange={(e) => setCustom(e.target.value)} placeholder={msg("Your own tag")} className="flex-1" />
          <button className="sc-mu-chip" type="submit">
            {msg("Add")}
          </button>
        </form>
      </PopoverContent>
    </Popover>
  );
}
