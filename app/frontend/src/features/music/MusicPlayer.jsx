// In-game music player (v1.8), at the bottom of the play screen's right panel. It plays what the story asks for
// (GET /stories/:id/music: the narrator's [Music:tag], else the scene's place, else any track) and crossfades when
// the track changes. Browsers block sound until the player clicks, hence "Turn the music on" the first time.
// Volume, mute and on/off are remembered in this browser.
import * as React from "react";
import * as Icon from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { apiGet } from "@/api/legacy";
import { msg } from "@/i18n";
import { navigate } from "@/lib/router";
import { cn } from "@/lib/util";
import { tagLabel, useMusicTags } from "@/features/music/tags";

const FADE_MS = 1800;

function stored(key, fallback) {
  try {
    let v = localStorage.getItem(key);
    return v == null ? fallback : JSON.parse(v);
  } catch {
    return fallback;
  }
}
function store(key, v) {
  try {
    localStorage.setItem(key, JSON.stringify(v));
  } catch {
    /* private mode */
  }
}
function fmt(s) {
  if (!isFinite(s)) return `0:00`;
  return `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, `0`)}`;
}

export function MusicPlayer({ storyId, refreshKey }) {
  let [on, setOn] = React.useState(() => stored(`sc:music-on`, false)),
    [volume, setVolume] = React.useState(() => stored(`sc:music-volume`, 0.5)),
    [muted, setMuted] = React.useState(() => stored(`sc:music-muted`, false)),
    [paused, setPaused] = React.useState(false),
    [skip, setSkip] = React.useState(0),
    [time, setTime] = React.useState({ cur: 0, dur: 0 }),
    tags = useMusicTags(),
    query = useQuery({
      queryKey: [`story-music`, storyId, skip, refreshKey],
      queryFn: () => apiGet(`/stories/${storyId}/music?skip=${skip}`),
      refetchInterval: 15_000,
    }),
    players = React.useRef([null, null]),
    active = React.useRef(0),
    playingId = React.useRef(null),
    target = muted ? 0 : volume,
    track = query.data?.track;

  // two <audio> elements: the next track fades in while the current one fades out
  if (!players.current[0] && typeof Audio !== `undefined`) {
    players.current = [new Audio(), new Audio()];
    players.current.forEach((a) => {
      a.loop = true;
      a.preload = `auto`;
    });
  }

  React.useEffect(
    () => () =>
      players.current.forEach((a) => {
        a?.pause();
        if (a) a.src = ``;
      }),
    [],
  );

  function fade(a, to, done) {
    let from = a.volume,
      start = performance.now();
    function step(now) {
      let k = Math.min(1, (now - start) / FADE_MS);
      a.volume = Math.max(0, Math.min(1, from + (to - from) * k));
      if (k < 1) requestAnimationFrame(step);
      else done?.();
    }
    requestAnimationFrame(step);
  }

  // switch track (crossfade) when the story's music changes
  React.useEffect(() => {
    if (!on || !track || track.id === playingId.current) return;
    let old = players.current[active.current],
      nextIdx = 1 - active.current,
      next = players.current[nextIdx];
    next.src = `/api/music/tracks/${track.id}/file`;
    next.volume = 0;
    next.currentTime = 0;
    next.play().then(
      () => fade(next, target),
      () => setOn(false), // the browser refused: ask for a click again
    );
    if (old && playingId.current) fade(old, 0, () => old.pause());
    active.current = nextIdx;
    playingId.current = track.id;
    setPaused(false);
  }, [on, track?.id]);

  // volume / mute follow at once on the playing element
  React.useEffect(() => {
    let a = players.current[active.current];
    if (a && playingId.current) a.volume = target;
    store(`sc:music-volume`, volume);
    store(`sc:music-muted`, muted);
  }, [volume, muted]);

  // progress bar
  React.useEffect(() => {
    let id = setInterval(() => {
      let a = players.current[active.current];
      if (a) setTime({ cur: a.currentTime || 0, dur: a.duration || 0 });
    }, 500);
    return () => clearInterval(id);
  }, []);

  function turnOn() {
    setOn(true);
    store(`sc:music-on`, true);
  }
  function turnOff() {
    players.current.forEach((a) => a?.pause());
    playingId.current = null;
    setOn(false);
    store(`sc:music-on`, false);
  }
  function togglePause() {
    let a = players.current[active.current];
    if (!a) return;
    if (a.paused) {
      a.play().catch(() => {});
      setPaused(false);
    } else {
      a.pause();
      setPaused(true);
    }
  }
  function seek(e) {
    let a = players.current[active.current],
      r = e.currentTarget.getBoundingClientRect();
    if (a && a.duration) a.currentTime = ((e.clientX - r.left) / r.width) * a.duration;
  }

  let data = query.data;
  if (!data) return null;
  if (!data.enabled) return null; // this world has no music (pack.json "music": false)
  if (!track)
    return (
      <div className="sc-mp sc-mp-empty">
        <Icon.Music className="size-4 shrink-0" />
        <span className="flex-1">{msg("No music in the library yet.")}</span>
        <button className="underline" onClick={() => navigate(`/music`)}>
          {msg("Add music")}
        </button>
      </div>
    );
  if (!on)
    return (
      <button className="sc-mp sc-mp-off" onClick={turnOn}>
        <Icon.Music className="size-4" /> {msg("Turn the music on")}
      </button>
    );
  let pct = time.dur ? (time.cur / time.dur) * 100 : 0;
  return (
    <div className="sc-mp">
      <div className="flex items-center gap-2">
        <Icon.Music className="size-4 shrink-0 text-[#e2bd72]" />
        <div className="min-w-0 flex-1">
          <p className="truncate text-xs font-semibold text-[#f3dca0]" title={track.title}>
            {track.title}
          </p>
          {data.tag && (
            <p className="truncate text-[10px] text-[#e2bd72aa]">
              {data.fallback
                ? msg("No “{{v0}}” track yet: random pick", { v0: tagLabel(tags.data, data.tag) })
                : `${tagLabel(tags.data, data.tag)}${data.source === `narrator` ? ` · ${msg("chosen by the narrator")}` : data.source === `location` ? ` · ${msg("from the place")}` : ``}`}
            </p>
          )}
        </div>
        <button className="sc-mp-btn" onClick={turnOff} title={msg("Turn the music off")} aria-label={msg("Turn the music off")}>
          <Icon.Power className="size-3.5" />
        </button>
      </div>
      <div className="sc-mp-bar" onClick={seek} role="slider" aria-label={msg("Position in the track")} aria-valuenow={Math.round(pct)}>
        <div className="sc-mp-fill" style={{ width: `${pct}%` }} />
      </div>
      <div className="flex items-center gap-1.5">
        <button className="sc-mp-main" onClick={togglePause} aria-label={paused ? msg("Play") : msg("Pause")}>
          {paused ? <Icon.Play className="size-4" /> : <Icon.Pause className="size-4" />}
        </button>
        <button className="sc-mp-btn" onClick={() => setSkip((s) => s + 1)} title={msg("Another track")} aria-label={msg("Another track")}>
          <Icon.SkipForward className="size-3.5" />
        </button>
        <span className="ml-1 text-[10px] tabular-nums text-[#e2bd72aa]">
          {fmt(time.cur)} / {fmt(time.dur)}
        </span>
        <button className="sc-mp-btn ml-auto" onClick={() => setMuted(!muted)} aria-label={muted ? msg("Unmute") : msg("Mute")}>
          {muted || volume === 0 ? <Icon.VolumeX className="size-3.5" /> : <Icon.Volume2 className="size-3.5" />}
        </button>
        <input
          type="range"
          min={0}
          max={1}
          step={0.01}
          value={muted ? 0 : volume}
          onChange={(e) => {
            setVolume(Number(e.target.value));
            setMuted(false);
          }}
          className={cn(`sc-mp-vol`)}
          aria-label={msg("Volume")}
          style={{ "--v": `${(muted ? 0 : volume) * 100}%` }}
        />
      </div>
    </div>
  );
}
