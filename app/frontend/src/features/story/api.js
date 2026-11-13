// Reconstructed from the StoryCore v1.7.0 compiled bundle (see DEVONLY/13_FRONTEND_SOURCE.md).
import { z } from "zod";
import { useQuery } from "@tanstack/react-query";
import { apiGet } from "@/api/legacy";

export var portraitFields = {
    asset_id: z.string().nullable().catch(null),
    slot_used: z.number().nullable().catch(null),
    is_fallback: z.boolean().catch(false),
  },
  beatSchema = z.object({
    character_id: z.string(),
    name: z.string().catch(``),
    expression: z.number().int().min(1).max(6).catch(1),
    evidence: z.string().catch(``),
    confidence: z.number().catch(0),
    ...portraitFields,
  }),
  sceneCharacterSchema = z.object({
    id: z.string(),
    label: z.string(),
    description: z.string().catch(``),
    kind: z.string().catch(`action`),
    approach: z.string().catch(``),
    format: z.string().catch(``),
  }),
  sceneSchema = z.object({
    character_id: z.string(),
    name: z.string().catch(``),
    expression: z.number().int().min(1).max(6).catch(1),
    beat: z.enum([`speaking`, `reacting`, `present`]).catch(`reacting`),
    anchor: z.string().nullable().catch(null),
    paragraph: z.number().int().nullable().catch(null),
    ...portraitFields,
  }),
  knownCharacterAxesSchema = z.object({
    character_id: z.string(),
    text: z.string(),
  }),
  knownCharacterSchema = z.object({
    source_id: z.string(),
    target_id: z.string(),
    source_name: z.string().catch(``),
    target_name: z.string().catch(``),
    dimension: z.string(),
    delta: z.number(),
    impact: z.string().catch(`minor`),
    evidence: z.string().catch(``),
    status: z.enum([`applied`, `proposed`]).catch(`applied`),
  }),
  knownListSchema = z.object({
    message_id: z.string().nullable(),
    story_id: z.string(),
    branch_id: z.string(),
    status: z.enum([`none`, `pending`, `running`, `succeeded`, `failed`, `skipped`, `stale`]).catch(`none`),
    error: z.string().nullable().catch(null),
    source: z.string().catch(`none`),
    is_head: z.boolean().catch(false),
    speakers: z.array(beatSchema).catch([]),
    active_speaker_id: z.string().nullable().catch(null),
    suggestions: z.array(sceneCharacterSchema).catch([]),
    suggestions_error: z.string().nullable().catch(null),
    beats: z.array(sceneSchema).catch([]),
    dialogue: z.array(knownCharacterAxesSchema).catch([]),
    relationship_changes: z.array(knownCharacterSchema).catch([]),
    settings: z
      .object({
        turn_analysis_mode: z.string().catch(`always`),
        action_suggestions_enabled: z.boolean().catch(true),
        show_scene_portraits: z.boolean().catch(true),
        relationship_mode: z.string().optional().catch(undefined),
      })
      .catch({
        turn_analysis_mode: `always`,
        action_suggestions_enabled: true,
        show_scene_portraits: true,
      }),
  }),
  characterDetailSchema = z
    .object({
      id: z.string().catch(``),
      target_name: z.string().catch(``),
      label: z.string().catch(``),
      axes: z.record(z.string(), z.number()).catch({}),
      note: z.string().optional().catch(``),
      history: z
        .array(
          z.object({
            at: z.string().catch(``),
            change: z.string().catch(``),
            source: z.string().catch(``),
            reason: z.string().optional().catch(``),
            source_replaced: z.boolean().optional().catch(false),
          }),
        )
        .catch([]),
    })
    .nullable()
    .catch(null),
  relationEventSchema = [`rumored`, `encountered`, `known`],
  knownCharactersSchema = z.object({
    characters: z
      .array(
        z.object({
          character_id: z.string(),
          name: z.string().catch(``),
          type: z.string().catch(``),
          local: z.boolean().catch(false),
          status: z.enum([`rumored`, `encountered`, `known`]).catch(`encountered`),
          capture_method: z.string().catch(``),
          evidence: z.string().catch(``),
          source_message_id: z.string().nullable().catch(null),
          source_seq: z.number().nullable().catch(null),
          discovered_at: z.string().nullable().catch(null),
          in_scene: z.boolean().catch(false),
          relationship: characterDetailSchema.optional(),
          ...portraitFields,
        }),
      )
      .catch([]),
  }),
  characterHistorySchema = z.object({
    id: z.string(),
    content: z.string().catch(``),
    fact_kind: z.string().catch(``),
    status: z.string().catch(``),
    source_seqs: z.array(z.number()).catch([]),
  }),
  knownCharacterDetailSchema = z.object({
    character: z.object({
      character_id: z.string(),
      name: z.string().catch(``),
      type: z.string().catch(``),
      local: z.boolean().catch(false),
    }),
    discovery_history: z
      .array(
        z.object({
          id: z.string(),
          status: z.string(),
          evidence: z.string().catch(``),
          capture_method: z.string().catch(``),
          created_at: z.string().catch(``),
          source_seq: z.number().nullable().catch(null),
        }),
      )
      .catch([]),
    relationship: characterDetailSchema,
    relationship_proposals: z
      .array(
        z.object({
          id: z.string(),
          status: z.string(),
          rationale: z.string().catch(``),
          confidence: z.number().catch(0),
          payload_json: z.record(z.string(), z.unknown()).catch({}),
          created_at: z.string().catch(``),
          source_seqs: z.array(z.number()).catch([]),
        }),
      )
      .catch([]),
    knowledge: z
      .object({
        knows: z.array(characterHistorySchema).catch([]),
        believes: z.array(characterHistorySchema).catch([]),
        unaware: z.array(characterHistorySchema).catch([]),
      })
      .catch({
        knows: [],
        believes: [],
        unaware: [],
      }),
    lore_relationships: z
      .array(
        z.object({
          source_id: z.string(),
          source_name: z.string().catch(``),
          target_id: z.string(),
          target_name: z.string().catch(``),
          type: z.string().catch(``),
          confidence: z.string().catch(``),
          lore_source: z.string().catch(``),
        }),
      )
      .catch([]),
    character_relationships: z
      .array(
        z.object({
          source_id: z.string(),
          source_name: z.string().catch(``),
          target_id: z.string().nullable().catch(null),
          target_name: z.string().catch(``),
          label: z.string().catch(``),
          axes: z.record(z.string(), z.number()).catch({}),
        }),
      )
      .catch([]),
    canon: z
      .array(
        z.object({
          type: z.string(),
          text: z.string(),
          source: z.string().catch(``),
          status: z.string().catch(`verified`),
        }),
      )
      .catch([]),
  }),
  sceneKeys = {
    scene: (e) => [`scene`, e],
    known: (e) => [`known-characters`, e],
    character: (e, t) => [`known-character`, e, t],
  },
  useScene = (e) =>
    useQuery({
      queryKey: sceneKeys.scene(e),
      queryFn: () => apiGet(`/stories/${e}/scene`, knownListSchema),
      refetchInterval: (e) =>
        e.state.data && (e.state.data.status === `pending` || e.state.data.status === `running`) ? 1500 : false,
    }),
  useKnownCharacters = (e) =>
    useQuery({
      queryKey: sceneKeys.known(e),
      queryFn: () => apiGet(`/stories/${e}/characters`, knownCharactersSchema).then((e) => e.characters),
    }),
  useKnownCharacter = (e, t) =>
    useQuery({
      queryKey: sceneKeys.character(e, t ?? ``),
      enabled: !!t,
      queryFn: () => apiGet(`/stories/${e}/characters/${t}`, knownCharacterDetailSchema),
    });
