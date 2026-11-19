// Shared react-query keys, response schemas and data hooks (stories, messages, state, providers, settings...).
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { apiGet } from "./legacy";
import { msg } from "@/i18n";

export const storySchema = z.looseObject({
  id: z.string(),
  title: z.string(),
  world_id: z.string().nullable(),
  world_name: z.string().nullable().optional(),
  active_avatar_id: z.string().nullable(),
  avatar_name: z.string().nullable().optional(),
  avatar_portrait: z.string().nullable().optional(),
  active_branch_id: z.string().nullable(),
  status: z.string(),
  settings_json: z.record(z.string(), z.any()),
  created_at: z.string(),
  updated_at: z.string(),
  last_activity: z.string().optional(),
  last_snippet: z.string().optional(),
  message_count: z.number().optional(),
});
export type Story = z.infer<typeof storySchema> & { branches?: any[] };

const storiesSchema = z.object({ stories: z.array(storySchema) });

export const chronoSchema = z.object({
  story_day: z.number().int().nullable().catch(null),
  weekday: z.string().nullable().catch(null),
  day: z.number().int().nullable().catch(null),
  month: z.string().nullable().catch(null),
  year: z.number().int().nullable().catch(null),
  date_text: z.string().nullable().catch(null),
  time: z.string().nullable().catch(null),
  weather: z.string().nullable().catch(null),
  location: z.string().nullable().catch(null),
  basis: z.string().nullable().catch(null),
  state_version: z.number().nullable().optional().catch(null),
  at: z.string().nullable().optional().catch(null),
});

export const messagesSchema = z.object({
  messages: z.array(
    z.looseObject({
      id: z.string(),
      story_id: z.string(),
      branch_id: z.string(),
      parent_id: z.string().nullable(),
      seq: z.number(),
      role: z.string(),
      kind: z.string(),
      speaker_character_id: z.string().nullable(),
      content: z.string(),
      command_json: z.record(z.string(), z.any()).nullable(),
      status: z.string(),
      created_at: z.string(),
      edited_at: z.string().nullable(),
      deleted_at: z.string().nullable(),
      generation: z.record(z.string(), z.any()).optional(),
      has_context: z.boolean().optional(),
      version_count: z.number().optional(),
      alternatives: z.object({ ids: z.array(z.string()), index: z.number(), leaf: z.array(z.boolean()) }).optional(),
      presentation: z
        .object({
          beats: z
            .array(
              z.object({
                character_id: z.string(),
                name: z.string().catch(""),
                expression: z.number().int().min(1).max(6).catch(1),
                beat: z.enum(["speaking", "reacting", "present"]).catch("reacting"),
                paragraph: z.number().int().nullable().catch(null),
                asset_id: z.string().nullable().catch(null),
              }),
            )
            .catch([]),
          dialogue: z.array(z.object({ character_id: z.string(), text: z.string() })).catch([]),
          paragraphs: z
            .array(z.object({ paragraph: z.number().int(), character_id: z.string().nullable(), name: z.string().nullable().catch(null) }))
            .optional()
            .catch(undefined),
        })
        .optional()
        .catch(undefined),
      immersive: z
        .object({
          items: z.array(
            z.object({
              source: z.enum(["player_authored", "ai_generated"]),
              text: z.string(),
              part: z.string().optional(),
              after: z.string().optional(),
            }),
          ),
        })
        .optional()
        .catch(undefined),
      immersive_reply_id: z.string().optional(),
      chrono: chronoSchema.optional().catch(undefined),
    }),
  ),
  branch_id: z.string(),
  deleted_hidden: z.number(),
  chronology: z
    .object({
      year_label: z.string().catch("Year"),
      year_start: z.string().catch("January"),
      provenance: z.string().nullable().catch(null),
    })
    .optional()
    .catch(undefined),
});
export type MessagesResponse = z.infer<typeof messagesSchema>;
export type Message = MessagesResponse["messages"][number];

export const streamEventSchema = z.discriminatedUnion("type", [
  z.object({ type: z.literal("snapshot"), text: z.string(), status: z.string() }),
  z.object({ type: z.literal("delta"), text: z.string() }),
  // v0.6: who speaks in each paragraph, found while the reply is written (backend services/live_speakers.py)
  z.object({ type: z.literal("portraits"), beats: z.array(z.any()) }),
  z.object({ type: z.literal("done"), status: z.string(), error: z.any().nullable().optional() }),
  z.object({ type: z.literal("ping") }),
  z.object({ type: z.literal("error"), error: z.any() }),
]);

/** The six portrait expressions (slot = image number in the character's folder). */
export const EXPRESSIONS = () => ([
  { slot: 1, short: msg("Neutral"), name: msg("Neutral") },
  { slot: 2, short: msg("Happy"), name: msg("Happy / Smiling") },
  { slot: 3, short: msg("Sad"), name: msg("Sad / Sobbing") },
  { slot: 4, short: msg("Angry"), name: msg("Angry / Aggressive") },
  { slot: 5, short: msg("Disdain"), name: msg("Disdain / Disgust") },
  { slot: 6, short: msg("Love"), name: msg("Love / Shy") },
]);

export const queryKeys = {
  stories: ["stories"],
  story: (id: string) => ["story", id],
  messages: (id: string) => ["messages", id],
  state: (id: string) => ["state", id],
  cast: (id: string) => ["cast", id],
  context: (id: string) => ["context", id],
  providers: ["providers"],
  settings: ["settings"],
  commands: (storyId?: string) => ["commands", storyId ?? ""],
  worlds: ["worlds"],
  avatars: ["avatars"],
  notes: (storyId?: string) => ["notes", storyId ?? ""],
  review: (id: string) => ["review", id],
  maintenance: (id: string) => ["maintenance", id],
};

export const useStories = () =>
  useQuery({ queryKey: queryKeys.stories, queryFn: () => apiGet("/stories", storiesSchema).then((r) => r.stories) });

export const useStory = (id: string) =>
  useQuery({
    queryKey: queryKeys.story(id),
    queryFn: () => apiGet<any>(`/stories/${id}`).then((r) => ({ ...storySchema.parse(r), branches: r.branches }) as Story),
  });

export const useMessages = (id: string) =>
  useQuery({ queryKey: queryKeys.messages(id), queryFn: () => apiGet(`/stories/${id}/messages`, messagesSchema) });

export const useStoryState = (id: string) =>
  useQuery({ queryKey: queryKeys.state(id), queryFn: () => apiGet<any>(`/stories/${id}/state`) });

export const useCast = (id: string) =>
  useQuery({ queryKey: queryKeys.cast(id), queryFn: () => apiGet<any>(`/stories/${id}/cast`).then((r) => r.cast) });

export const useContextPreview = (id: string, enabled = true) =>
  useQuery({ queryKey: queryKeys.context(id), enabled, queryFn: () => apiGet<any>(`/stories/${id}/context`) });

export const useProviders = () => useQuery({ queryKey: queryKeys.providers, queryFn: () => apiGet<any>("/providers") });

export const useSettings = () => useQuery({ queryKey: queryKeys.settings, queryFn: () => apiGet<any>("/settings") });

export const useCommands = (storyId?: string) =>
  useQuery({
    queryKey: queryKeys.commands(storyId),
    queryFn: () => apiGet<any>(`/commands${storyId ? `?story_id=${storyId}` : ""}`).then((r) => r.commands),
  });

export const useWorlds = () =>
  useQuery({ queryKey: queryKeys.worlds, queryFn: () => apiGet<any>("/worlds").then((r) => r.worlds) });

export const useAvatars = () =>
  useQuery({ queryKey: queryKeys.avatars, queryFn: () => apiGet<any>("/avatars").then((r) => r.avatars) });

export const useReviewCount = (id: string) =>
  useQuery({
    queryKey: queryKeys.review(id),
    queryFn: () => apiGet<any>(`/stories/${id}/review`).then((r) => r.count),
    refetchInterval: 20_000,
  });

/** After a change to a story: refresh everything that shows it. */
export function useInvalidateStory() {
  const queryClient = useQueryClient();
  return (storyId: string) => {
    for (const key of [
      queryKeys.messages(storyId),
      queryKeys.state(storyId),
      queryKeys.cast(storyId),
      queryKeys.context(storyId),
      queryKeys.story(storyId),
      queryKeys.review(storyId),
      queryKeys.maintenance(storyId),
    ])
      queryClient.invalidateQueries({ queryKey: key });
    for (const key of [["scene", storyId], ["known-characters", storyId], ["known-character", storyId]])
      queryClient.invalidateQueries({ queryKey: key });
    queryClient.invalidateQueries({ queryKey: ["journal", storyId] });
    queryClient.invalidateQueries({ queryKey: queryKeys.stories });
  };
}
