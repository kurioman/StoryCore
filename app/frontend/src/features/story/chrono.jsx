// Reconstructed from the StoryCore v1.7.0 compiled bundle (see DEVONLY/13_FRONTEND_SOURCE.md).
import * as Icon from "lucide-react";
import { msg } from "@/i18n";
import { cn } from "@/lib/util";

export var WEEKDAYS = [`Monday`, `Tuesday`, `Wednesday`, `Thursday`, `Friday`, `Saturday`, `Sunday`],
  MONTHS = [
    `January`,
    `February`,
    `March`,
    `April`,
    `May`,
    `June`,
    `July`,
    `August`,
    `September`,
    `October`,
    `November`,
    `December`,
  ];

function weatherIcon(e) {
  let t = e.toLowerCase();
  return (
    [
      [/thunder|storm|lightning/, `⛈️`],
      [/snow|sleet|blizzard|frost/, `❄️`],
      [/rain|drizzle|shower|downpour/, `🌧️`],
      [/fog|mist|haze/, `🌫️`],
      [/wind|gust|breez|gale/, `💨`],
      [/overcast|cloud|grey|gray/, `☁️`],
      [/clear|sun|bright|cloudless/, `☀️`],
      [/night|star|moon/, `🌙`],
    ].find(([e]) => e.test(t))?.[1] ?? ``
  );
}

function chronoParts(e, t = msg("Year", {})) {
  let n = [];
  n.push(
    e.story_day
      ? {
          key: `day`,
          text: `D${e.story_day}`,
          known: true,
          title: msg("In-story day {{v0}} (D1 is the first day of the story)", {
            v0: e.story_day,
          }),
        }
      : {
          key: `day`,
          text: msg("Day not tracked", {}),
          known: false,
          title: msg("The day count was not tracked when this reply was written"),
        },
  );
  // month and weekday names come from the story data in English: translated for display only
  let r = e.month ? MONTHS.indexOf(e.month) + 1 : 0,
    month = e.month ? msg(e.month) : e.month,
    weekday = e.weekday ? msg(e.weekday) : e.weekday,
    i = null;
  e.year && r && e.day
    ? (i = `${t} ${e.year}/${r}/${e.day}`)
    : r && e.day
      ? (i = `${e.day} ${month}${e.year ? `, ${t} ${e.year}` : msg(", year unknown", {})}`)
      : e.month
        ? (i = `${month}${e.year ? ` ${t} ${e.year}` : ``}`)
        : e.year
          ? (i = `${t} ${e.year}`)
          : e.date_text && (i = e.date_text);
  let a = e.year && e.month && e.day ? `${e.day} ${month}, ${t} ${e.year}` : i;
  return (
    i &&
      n.push({
        key: `date`,
        text: i,
        known: true,
        title: msg("Date: {{v0}}", { v0: a }),
      }),
    e.weekday &&
      n.push({
        key: `weekday`,
        text: weekday,
        known: true,
        title: msg("Weekday: {{v0}}", { v0: weekday }),
      }),
    !i && !e.weekday
      ? n.push({
          key: `date`,
          text: msg("Date not established", {}),
          known: false,
          title: msg("No in-story date has been established yet", {}),
        })
      : e.weekday ||
        n.push({
          key: `weekday`,
          text: msg("Weekday unknown", {}),
          known: false,
          title: msg("The weekday has not been established", {}),
        }),
    n.push(
      e.time
        ? {
            key: `time`,
            text: e.time,
            known: true,
            title: msg("Time: {{v0}}", {
              v0: e.time,
            }),
          }
        : {
            key: `time`,
            text: msg("Time not established", {}),
            known: false,
            title: msg(
              "The story has not stated a time yet. It is never guessed; a stated hour or time of day appears here.",
            ),
          },
    ),
    n.push(
      e.weather
        ? {
            key: `weather`,
            text: e.weather.charAt(0).toUpperCase() + e.weather.slice(1),
            known: true,
            title: msg("Weather: {{v0}}", {
              v0: e.weather,
            }),
            icon: weatherIcon(e.weather),
          }
        : {
            key: `weather`,
            text: msg("Weather not established", {}),
            known: false,
            title: msg("The weather has not been established"),
          },
    ),
    n.push(
      e.location
        ? {
            key: `location`,
            text: e.location,
            known: true,
            title: msg("Location: {{v0}}", {
              v0: e.location,
            }),
          }
        : {
            key: `location`,
            text: msg("Place unknown", {}),
            known: false,
            title: msg("The location has not been established"),
          },
    ),
    n
  );
}

var CHRONO_TONES = {
  before_reply: msg("Scene as it stood when this reply began (updated once the reply has been analysed)", {}),
  analysis: msg("Scene for this reply, including what the reply established", {}),
  manual: msg("Scene as you corrected it", {}),
  reconstructed: msg("Reconstructed from the story's saved state history (this reply predates per-reply headers)", {}),
};

export function ChronoHeader({ c, yearLabel, onEdit, pending }) {
  if (c.basis === `not_recorded`)
    return (
      <p
        className="story-chrono mb-2 border-b border-line pb-1 text-[11px] italic text-faint"
        title={msg("This older reply was written before scene details were saved")}
      >
        {msg("Scene not recorded for this reply")}
      </p>
    );

  let i = chronoParts(c, yearLabel),
    a = i.map((e) => e.text).join(`, `);
  return (
    <div
      className={cn(
        `story-chrono mb-2.5 flex min-w-0 flex-wrap items-center gap-x-1.5 gap-y-0.5 border-b border-line pb-1.5 text-xs leading-5 text-muted`,
        pending && `opacity-70`,
      )}
      role="group"
      aria-label={msg("In-story scene: {{v0}}", {
        v0: a,
      })}
      aria-busy={pending || undefined}
      title={CHRONO_TONES[c.basis ?? ``] ?? undefined}
      data-basis={c.basis ?? undefined}
    >
      {i.map((e, t) => (
        <span className="inline-flex min-w-0 max-w-full items-center gap-1.5" key={e.key}>
          <span
            className={cn(
              `min-w-0 [overflow-wrap:anywhere]`,
              e.key === `day` && e.known && `font-semibold text-fg`,
              !e.known && `italic text-faint`,
            )}
            title={e.title}
          >
            {e.icon && (
              <span aria-hidden className="mr-1 not-italic">
                {e.icon}
              </span>
            )}
            {e.text}
          </span>
          {t < i.length - 1 && (
            <span aria-hidden className="select-none text-faint">
              |
            </span>
          )}
        </span>
      ))}
      {c.basis === `reconstructed` && (
        <span className="text-faint" title={CHRONO_TONES.reconstructed}>
          <span aria-hidden>≈</span>
          <span className="sr-only">{msg("(reconstructed from saved state)")}</span>
        </span>
      )}
      {onEdit && (
        <button
          type="button"
          onClick={onEdit}
          className="ml-0.5 inline-flex size-6 shrink-0 items-center justify-center rounded text-faint hover:bg-panel-2 hover:text-fg"
          aria-label={msg("Correct the current scene (day, date, time, weather, place)")}
          title={msg("Correct the current scene (also /scene)")}
        >
          <Icon.Pencil className="size-3.5" />
        </button>
      )}
    </div>
  );
}
