// Reconstructed from the StoryCore v1.7.0 compiled bundle (see DEVONLY/13_FRONTEND_SOURCE.md).
import { useSettings, useProviders } from "@/api/queries";
import * as React from "react";
import { msg } from "@/i18n";
import { Button, Callout, Field, Input, SectionTitle, Select, Spinner, Toggle } from "@/components/ui";
import { useSaveSettings } from "@/features/settings/SettingsPage";

export function MemorySettings() {
  let settings = useSettings(),
    providers = useProviders(),
    saveSettings = useSaveSettings(),
    [r, i] = React.useState(null);
  return (
    React.useEffect(() => {
      settings.data && !r && i(structuredClone(settings.data));
    }, [settings.data, r]),
    r ? (
      <div className="max-w-3xl space-y-5">
        <Callout tone="info">
          {msg(
            "The journal records what happens in play (events, facts, proposed state changes) with links to the source messages. Capturing uses an extra model call; with cloud providers that can cost money. The transcript itself is always saved, whatever you choose here.",
          )}
        </Callout>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label={msg("Automatic event capture")}>
            <Select
              value={r.event_capture_mode}
              onChange={(e) =>
                i({
                  ...r,
                  event_capture_mode: e.target.value,
                })
              }
            >
              <option value="batch">{msg("Batch — every N replies (default)")}</option>
              <option value="after_each_turn">{msg("After each reply (more calls)")}</option>
              <option value="manual">{msg("Manual only (“Save important events now”)")}</option>
              <option value="off">{msg("Off")}</option>
            </Select>
          </Field>
          <Field label={msg("Batch size (replies)")}>
            <Input
              type="number"
              min={1}
              max={20}
              value={r.event_capture_batch_turns}
              disabled={r.event_capture_mode !== `batch`}
              onChange={(e) =>
                i({
                  ...r,
                  event_capture_batch_turns: Number(e.target.value),
                })
              }
            />
          </Field>
          <Field label={msg("Extraction model")}>
            <Select
              value={r.extraction_model_source}
              onChange={(e) =>
                i({
                  ...r,
                  extraction_model_source: e.target.value,
                })
              }
            >
              <option value="narration">{msg("Same as the story's narration model")}</option>
              <option value="separate">{msg("A separate model")}</option>
              <option value="none">{msg("None (disable model-based capture)")}</option>
            </Select>
          </Field>
          {r.extraction_model_source === `separate` && (
            <Field label={msg("Separate extraction/recap model")}>
              <Select
                value={r.extraction_model_profile_id ?? ``}
                onChange={(e) =>
                  i({
                    ...r,
                    extraction_model_profile_id: e.target.value || null,
                  })
                }
              >
                <option value="">{msg("Choose…")}</option>
                {providers.data?.profiles.map((e) => (
                  <option value={e.id} key={e.id}>
                    {e.display_name}
                  </option>
                ))}
              </Select>
            </Field>
          )}
          <Field
            label={msg("Clearly narrated events are stored as")}
            hint={msg("Uncertain, claimed, rumoured or uncited events always go to the review queue.")}
          >
            <Select
              value={r.event_auto_store_status}
              onChange={(e) =>
                i({
                  ...r,
                  event_auto_store_status: e.target.value,
                })
              }
            >
              <option value="recorded_unverified">{msg("Recorded (unverified)")}</option>
              <option value="confirmed_from_transcript">{msg("Confirmed from transcript")}</option>
              <option value="candidate">{msg("Candidate (review everything)")}</option>
            </Select>
          </Field>
          <Field label={msg("Review threshold (confidence below → review queue)")}>
            <Input
              type="number"
              step={0.05}
              min={0}
              max={1}
              value={r.candidate_confidence_threshold}
              onChange={(e) =>
                i({
                  ...r,
                  candidate_confidence_threshold: Number(e.target.value),
                })
              }
            />
          </Field>
        </div>
        <SectionTitle>{msg("Scene analysis after each reply")}</SectionTitle>
        <p className="text-xs text-muted">
          {msg(
            "On by default. After each completed reply it finds who is speaking and reacting (portraits), writes three suggested replies, and updates relationships. It is one extra request per reply, billed on a paid model. It never changes the story text; if it fails, the reply stays and you see the reason with a Retry button. Incomplete replies are not analysed.",
          )}
        </p>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field
            label={msg("Run scene analysis")}
            hint={msg("Uses the extraction model above, or the narration model.")}
          >
            <Select
              value={r.turn_analysis_mode ?? `always`}
              onChange={(e) =>
                i({
                  ...r,
                  turn_analysis_mode: e.target.value,
                })
              }
              aria-label={msg("Run scene analysis")}
            >
              <option value="always">{msg("Automatic: every model, including hosted ones (default)")}</option>
              <option value="local_only">{msg("Local models only")}</option>
              <option value="off">{msg("Off")}</option>
            </Select>
          </Field>
          <Field
            label={msg("Relationship changes")}
            hint={msg(
              "Evaluated after every reply; a neutral scene changes nothing. Every change keeps its reason and can be undone. Off keeps existing relationships as they are.",
            )}
          >
            <Select
              value={r.relationship_mode ?? `auto_conservative`}
              onChange={(e) =>
                i({
                  ...r,
                  relationship_mode: e.target.value,
                })
              }
              aria-label={msg("Relationship changes")}
            >
              <option value="auto_conservative">
                {msg("Automatic (default): small, clear changes apply; big ones wait for review")}
              </option>
              <option value="review">{msg("Review every change")}</option>
              <option value="off">{msg("Off")}</option>
            </Select>
          </Field>
          <Field
            label={msg("Where portraits appear")}
            hint={msg("Only changes what you see. Characters are still detected.")}
          >
            <Select
              value={
                r.show_scene_portraits === false
                  ? r.inline_portraits === false
                    ? `hidden`
                    : `story`
                  : r.inline_portraits === false
                    ? `strip`
                    : `both`
              }
              onChange={(e) =>
                i({
                  ...r,
                  show_scene_portraits: e.target.value === `both` || e.target.value === `strip`,
                  inline_portraits: e.target.value === `both` || e.target.value === `story`,
                })
              }
              aria-label={msg("Where portraits appear")}
            >
              <option value="both">{msg("In the story text and above the message box (default)")}</option>
              <option value="story">{msg("In the story text only")}</option>
              <option value="strip">{msg("Above the message box only")}</option>
              <option value="hidden">{msg("Hidden")}</option>
            </Select>
          </Field>
        </div>
        {r.turn_analysis_mode === `off` && (
          <Callout tone="info">
            {msg(
              "Suggested replies, relationship tracking and expressions chosen from the scene need scene analysis, so they do not run while it is off. Your saved relationships and stories are kept.",
            )}
          </Callout>
        )}
        <Toggle
          checked={r.action_suggestions_enabled ?? true}
          onChange={(e) =>
            i({
              ...r,
              action_suggestions_enabled: e,
            })
          }
          label={msg("Suggest three replies")}
          description={msg(
            "Shown under the latest reply. Picking one only fills the message box; nothing is sent for you.",
          )}
        />
        <Toggle
          checked={r.auto_apply_expression_suggestions ?? true}
          onChange={(e) =>
            i({
              ...r,
              auto_apply_expression_suggestions: e,
            })
          }
          label={msg("Update portrait expressions automatically")}
          description={msg("Off keeps the expressions you set yourself. Locked portraits never change either way.")}
        />
        <Toggle
          checked={r.recap_auto_replace}
          onChange={(e) =>
            i({
              ...r,
              recap_auto_replace: e,
            })
          }
          label={msg("Generated recaps replace the rolling recap automatically")}
          description={msg("Off: new recaps are candidates you accept.")}
        />
        <Callout tone="warn">
          {msg(
            "AI-proposed changes to stats, inventory, injuries, quests and canon always wait for your approval in the review queue. Relationships follow the “Relationship changes” choice above: in Automatic (conservative) mode small, clearly evidenced changes apply at once (undone with their reply); larger or uncertain ones wait for review.",
          )}
        </Callout>
        <Button
          variant="primary"
          loading={saveSettings.isPending}
          onClick={() =>
            saveSettings.mutate({
              event_capture_mode: r.event_capture_mode,
              event_capture_batch_turns: r.event_capture_batch_turns,
              extraction_model_source: r.extraction_model_source,
              extraction_model_profile_id: r.extraction_model_profile_id,
              event_auto_store_status: r.event_auto_store_status,
              candidate_confidence_threshold: r.candidate_confidence_threshold,
              auto_apply_expression_suggestions: r.auto_apply_expression_suggestions,
              recap_auto_replace: r.recap_auto_replace,
              turn_analysis_mode: r.turn_analysis_mode,
              relationship_mode: r.relationship_mode,
              action_suggestions_enabled: r.action_suggestions_enabled,
              show_scene_portraits: r.show_scene_portraits,
              inline_portraits: r.inline_portraits,
            })
          }
        >
          {msg("Save")}
        </Button>
      </div>
    ) : (
      <Spinner />
    )
  );
}
