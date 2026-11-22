// Token counter of the play screen (v0.5 phase 7.5): what the latest turn sent (and how much came from the provider's
// cache), and what the whole story used, narrator and side requests (scene analysis, memory, summaries, recap).
// Figures are the provider's own; "≈" marks the app's estimate when the provider reports nothing (some local servers).
import * as React from "react";
import * as Icon from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { apiGet } from "@/api/legacy";
import { msg, shownLanguage } from "@/i18n";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui";
import { fmtK } from "@/lib/util";

function num(n) {
  return typeof n === `number` ? n.toLocaleString(shownLanguage()) : `—`;
}

// v0.6.2: three decimals under one dollar ($0.017), so the figure can be compared with the provider's own page
function money(c) {
  if (typeof c !== `number` || c <= 0) return null;
  return `$${c >= 1 ? c.toFixed(2) : c >= 0.001 ? c.toFixed(3) : c.toFixed(4)}`;
}

const KIND_LABELS = () => ({
  analysis: msg("Scene analysis"),
  capture: msg("Memory capture"),
  summary: msg("Summaries"),
  recap: msg("Recaps"),
});

export function UsageMeter({ storyId, refreshKey }) {
  let query = useQuery({
      queryKey: [`usage`, storyId, refreshKey],
      queryFn: () => apiGet(`/stories/${storyId}/usage`),
      staleTime: 10000,
      refetchInterval: 30000, // side requests (analysis, recaps) are paid after the reply
    }),
    d = query.data;
  if (!d || !d.last) return null;
  let last = d.last,
    input = last.input ?? last.estimated_input,
    cachedShare = last.cached && last.input ? Math.round((100 * last.cached) / last.input) : null,
    labels = KIND_LABELS(),
    cost = money(d.total.cost);
  return (
    <Popover>
      <PopoverTrigger asChild>
        {cost ? (
          // v0.6.2: the money spent is the figure a newcomer cares about most: always shown, phone included
          <button
            type="button"
            className="flex items-center gap-1 rounded-md border border-[#e9c46a55] bg-[#e9c46a14] px-2 py-0.5 text-xs font-semibold text-[#f3dca0] hover:bg-[#e9c46a26]"
            title={msg("Money spent on this story — click for the details")}
          >
            <Icon.Coins className="size-3.5" />
            <span>{cost}</span>
          </button>
        ) : (
          <button
            type="button"
            className="flex items-center gap-1 rounded-md px-2 py-1 text-xs text-muted hover:bg-panel-2"
            title={msg("Tokens used by the latest turn — click for the details")}
          >
            <Icon.Gauge className="size-3.5" />
            <span className="hidden md:inline">
              {last.input == null ? `≈` : ``}
              {fmtK(input ?? 0)}
              {cachedShare ? ` · ${msg("{{v0}}% cached", { v0: cachedShare })}` : ``}
            </span>
          </button>
        )}
      </PopoverTrigger>
      <PopoverContent align="end" className="w-80 max-w-[calc(100vw-1rem)] p-3 text-xs">
        {cost && (
          <div className="mb-3 rounded-md border border-[#e9c46a55] bg-[#e9c46a14] px-3 py-2">
            <p className="text-[11px] text-muted">{msg("Spent on this story")}</p>
            <p className="text-xl font-semibold text-[#f3dca0]">{cost}</p>
            <p className="mt-1 text-[11px] text-faint">
              {msg(
                "As billed by the provider: every request counts, regenerated or removed replies included. Tests made in the settings are not part of it.",
              )}
            </p>
          </div>
        )}
        <p className="mb-1 font-semibold text-fg">{msg("Latest turn")}</p>
        <dl className="grid grid-cols-[1fr_auto] gap-x-3 gap-y-0.5 text-muted">
          <dt>{msg("Sent to the AI")}</dt>
          <dd className="text-right">
            {last.input == null ? `≈${num(last.estimated_input)} (${msg("estimate")})` : num(last.input)}
          </dd>
          {last.cached != null && (
            <>
              <dt>{msg("…of which from the cache")}</dt>
              <dd className="text-right">{num(last.cached)}</dd>
            </>
          )}
          <dt>{msg("Written by the AI")}</dt>
          <dd className="text-right">{num(last.output)}</dd>
        </dl>
        <p className="mb-1 mt-3 font-semibold text-fg">{msg("Whole story")}</p>
        <dl className="grid grid-cols-[1fr_auto] gap-x-3 gap-y-0.5 text-muted">
          <dt>{msg("Narrator ({{v0}} replies)", { v0: d.narration.requests ?? 0 })}</dt>
          <dd className="text-right">{num((d.narration.input ?? 0) + (d.narration.output ?? 0))}</dd>
          {Object.entries(d.side).map(([k, v]) => (
            <React.Fragment key={k}>
              <dt>
                {labels[k] ?? k} ({v.requests})
              </dt>
              <dd className="text-right">{num((v.input ?? 0) + (v.output ?? 0))}</dd>
            </React.Fragment>
          ))}
          <dt className="font-medium text-fg">{msg("Total tokens")}</dt>
          <dd className="text-right font-medium text-fg">{num((d.total.input ?? 0) + (d.total.output ?? 0))}</dd>
          {d.total.cached ? (
            <>
              <dt>{msg("…of which read from the cache")}</dt>
              <dd className="text-right">{num(d.total.cached)}</dd>
            </>
          ) : null}
        </dl>
        {d.total.unreported ? (
          <p className="mt-2 text-faint">
            {msg("{{v0}} request(s) without figures from the provider are not counted in the totals.", {
              v0: d.total.unreported,
            })}
          </p>
        ) : null}
      </PopoverContent>
    </Popover>
  );
}
