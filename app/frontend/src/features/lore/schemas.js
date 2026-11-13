// Reconstructed from the StoryCore v1.7.0 compiled bundle (see DEVONLY/13_FRONTEND_SOURCE.md).
import { z } from "zod";
import { useStoryState, useInvalidateStory } from "@/api/queries";
import { useMutation } from "@tanstack/react-query";
import { apiPut, errorMessage, apiPost } from "@/api/legacy";
import { useUi } from "@/components/ui";

export var zText = z
    .string()
    .nullish()
    .transform((e) => e ?? ``),
  zStringList = z
    .array(z.unknown())
    .nullish()
    .transform((e) => (e ?? []).filter((e) => typeof e == `string`)),
  loreEntitySchema = z.object({
    id: z.string(),
    entity_id: z.string(),
    category: zText,
    type: zText,
    name: z
      .string()
      .nullish()
      .transform((e) => e || `Unnamed record`),
    aliases: zStringList,
    summary: zText,
    confidence: z
      .string()
      .nullish()
      .transform((e) => e ?? null),
    canon_status: z
      .string()
      .nullish()
      .transform((e) => e ?? null),
    source_ids: zStringList,
    file: zText,
  }),
  loreEntitiesSchema = z.object({
    entities: z
      .array(loreEntitySchema)
      .nullish()
      .transform((e) => e ?? []),
  }),
  loreEntityDetailSchema = z.object({
    entity: loreEntitySchema.extend({
      data: z
        .record(z.string(), z.unknown())
        .nullish()
        .transform((e) => e ?? {}),
      chunk_id: z
        .string()
        .nullish()
        .transform((e) => e ?? null),
    }),
    sources: z
      .array(
        z.object({
          id: z.string(),
          title: zText,
          url: z.string().nullish(),
          reliability: z.string().nullish(),
        }),
      )
      .nullish()
      .transform((e) => e ?? []),
    local_canon: z
      .array(
        z.object({
          id: z.string(),
          title: zText,
          content: zText,
          status: zText,
        }),
      )
      .nullish()
      .transform((e) => e ?? []),
  }),
  loreWorldSummarySchema = z.object({
    categories: z
      .record(z.string(), z.number())
      .nullish()
      .transform((e) => e ?? {}),
    last_import: z
      .object({
        status: zText,
        finished_at: z.string().nullish(),
        report_json: z
          .record(z.string(), z.unknown())
          .nullish()
          .transform((e) => e ?? {}),
      })
      .nullish()
      .transform((e) => e ?? null),
  }),
  loreSearchSchema = z.object({
    results: z
      .array(
        z.object({
          chunk_id: z.string(),
          title: zText,
          category: zText,
          entity_id: z.string().nullish(),
          snippet: zText,
          confidence: z.string().nullish(),
          canon_status: z.string().nullish(),
        }),
      )
      .nullish()
      .transform((e) => e ?? []),
    local_canon: z
      .array(
        z.object({
          id: z.string(),
          title: zText,
          content: zText,
          status: zText,
        }),
      )
      .nullish()
      .transform((e) => e ?? []),
  }),
  countOf = (e, t) => (Array.isArray(e[t]) ? e[t].length : 0);

export function useStateEditor(e) {
  let storyState = useStoryState(e),
    invalidateStory = useInvalidateStory(),
    { toast } = useUi(),
    mutation = useMutation({
      mutationFn: ({ state, summary }) =>
        apiPut(`/stories/${e}/state`, {
          state,
          summary,
          base_version: storyState.data?.version,
        }),
      onSuccess: () => invalidateStory(e),
      onError: (t) => {
        (toast(errorMessage(t), `danger`), invalidateStory(e));
      },
    }),
    a = useMutation({
      mutationFn: (t) => apiPost(`/stories/${e}/state/change`, t),
      onSuccess: () => invalidateStory(e),
      onError: (e) => toast(errorMessage(e), `danger`),
    });
  return {
    q: storyState,
    state: storyState.data?.state,
    version: storyState.data?.version,
    save: (e, n) => {
      if (!storyState.data) return;
      let r = structuredClone(storyState.data.state);
      (e(r),
        mutation.mutate({
          state: r,
          summary: n,
        }));
    },
    change: a,
    saving: mutation.isPending || a.isPending,
  };
}
