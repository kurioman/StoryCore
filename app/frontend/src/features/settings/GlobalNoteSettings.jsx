// Reconstructed from the StoryCore v1.7.0 compiled bundle (see DEVONLY/13_FRONTEND_SOURCE.md).
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { queryKeys } from "@/api/queries";
import { apiGet, apiPut } from "@/api/legacy";
import * as React from "react";
import * as Icon from "lucide-react";
import { msg } from "@/i18n";
import { Button, Spinner, Textarea, Toggle, useUi } from "@/components/ui";
import { downloadJson } from "@/lib/util";

export function GlobalNoteSettings() {
  let query = useQuery({
      queryKey: queryKeys.notes(),
      queryFn: () => apiGet(`/notes`),
    }),
    queryClient = useQueryClient(),
    { toast } = useUi(),
    [r, i] = React.useState(null);
  return (
    React.useEffect(() => {
      query.data && !r && i(query.data.global);
    }, [query.data, r]),
    r ? (
      <div className="max-w-3xl space-y-3">
        <p className="text-sm text-muted">
          {msg(
            "Applies to every story unless a story disables it (Notes button in the story's top bar). Story notes take precedence.",
          )}
        </p>
        <Toggle
          checked={r.enabled}
          onChange={(e) =>
            i({
              ...r,
              enabled: e,
            })
          }
          label={msg("Enabled")}
        />
        <Textarea
          value={r.content}
          onChange={(e) =>
            i({
              ...r,
              content: e.target.value,
            })
          }
          className="min-h-60"
          aria-label={msg("Global note")}
        />
        <p className="text-xs text-faint">
          ≈{Math.ceil(r.content.length / 4)} {msg("tokens")}
        </p>
        <div className="flex gap-2">
          <Button
            variant="primary"
            onClick={async () => {
              (await apiPut(`/notes/${r.id}`, {
                content: r.content,
                enabled: r.enabled,
              }),
                queryClient.invalidateQueries({
                  queryKey: [`notes`],
                }),
                toast(msg("Global note saved")));
            }}
          >
            {msg("Save")}
          </Button>
          <Button
            variant="ghost"
            onClick={async () => downloadJson(`storycore-notes.json`, await apiGet(`/notes/export`))}
          >
            <Icon.Download className="size-4" /> {msg("Export notes")}
          </Button>
        </div>
      </div>
    ) : (
      <Spinner />
    )
  );
}
