// Reconstructed from the StoryCore v1.7.0 compiled bundle (see DEVONLY/13_FRONTEND_SOURCE.md).
import * as React from "react";
import { msg } from "@/i18n";
import { Button, Modal } from "@/components/ui";
import { navigate } from "@/lib/router";

var focusTarget =
    (e, t = false) =>
    () => {
      let n = document.querySelector(e);
      (n?.scrollIntoView({
        block: `center`,
      }),
        t && n?.focus());
    },
  TOUR_STEPS = [
    {
      title: msg("Write what you do"),
      body: msg(
        "The message box at the bottom is yours. Describe what your character does and says; only you decide that. Press Enter to send. Type / to see commands, such as /recap.",
      ),
      show: {
        label: msg("Go to the message box"),
        run: focusTarget(`#story-composer`, true),
        needs: `#story-composer`,
      },
    },
    {
      title: msg("Read the scene"),
      body: msg(
        "Spoken words stand out; narration is a quieter grey. A name appears when the speaker changes, and portraits sit beside the moment a character acts. Each reply starts with its in-story day, time, weather and place. You can change the text size.",
      ),
      show: {
        label: msg("Open reading settings"),
        run: () => navigate(`/settings/appearance`),
      },
    },
    {
      title: msg("Use a suggestion, or don't"),
      body: msg(
        "After a reply, three drafts appear. Choosing one only puts it in your message box, so you can edit it. Nothing is sent until you press Send, and your own unsent text is never replaced without asking.",
      ),
      show: {
        label: msg("Show the suggestions"),
        run: focusTarget(`[aria-label="Next action"]`),
        needs: `[aria-label="Next action"]`,
      },
    },
    {
      title: msg("Characters and memory"),
      body: msg(
        "The panel button at the top right shows who is here, who you know and how they see you. Journal & Memory keeps events and facts, with links back to the messages they came from. If relationship review is on, changes wait for you to accept them.",
      ),
    },
    {
      title: msg("Choose an AI"),
      body: msg(
        "OpenRouter gives access to powerful hosted models and is billed per use. Ollama runs models on your own computer. Settings has a short guide for both, and the current model is always shown next to Send.",
      ),
      show: {
        label: msg("Open model settings"),
        run: () => navigate(`/settings/providers`),
      },
    },
    {
      title: msg("Fix things and stay safe"),
      body: msg(
        "The pencil at the end of the latest reply's header corrects the scene (also /scene). The More menu has savepoints and notes. Settings has backups, and logs for reporting a problem.",
      ),
      show: {
        label: msg("Open backups"),
        run: () => navigate(`/settings/data`),
      },
    },
  ],
  FAQ = [
    {
      q: msg("Why does a reply say “Time not established”?"),
      a: msg(
        "The story has not stated a time yet. The app never guesses one. When a reply mentions an hour or a time of day it appears there, and you can set it yourself with the pencil or /scene.",
      ),
    },
    {
      q: msg("Why did a relationship not change?"),
      a: msg(
        "In “Review every change” mode, changes wait in the review queue in Journal & Memory. Automatic (conservative) mode applies small, clear changes at once; switch in Settings → Memory capture.",
      ),
    },
    {
      q: msg("Why was a reply cut off?"),
      a: msg(
        "The model reached its output limit, sometimes on hidden reasoning before writing. The reply is marked incomplete and gets no suggestions. Retry sends a new request, billed on a paid model. The ⓘ button under a reply shows how it ended.",
      ),
    },
    {
      q: msg("Which model am I using?"),
      a: msg(
        "Its name is shown next to Send, and each reply lists the model that wrote it. The model menu in the top bar changes it for this story.",
      ),
    },
    {
      q: msg("How do I back up my stories?"),
      a: msg("Settings → Data & backups → Back up now. API keys are never included in a backup."),
    },
    {
      q: msg("Why are local models less consistent?"),
      a: msg(
        "Smaller models have less room for long context, many characters and strict formats. A larger local model or a hosted model usually helps.",
      ),
    },
    {
      q: msg("Where can I see costs and logs?"),
      a: msg(
        "OpenRouter's Activity page shows what you spent. Replies on OpenRouter show their reported cost when you hover over them. App logs are in Settings → Data & backups.",
      ),
    },
  ];

export function HelpDialog({ open, onClose }) {
  let [n, r] = React.useState(0),
    [i, a] = React.useState(false),
    o = TOUR_STEPS[n],
    s = () => {
      (onClose(), a(false));
    },
    c = !o.show?.needs || !!document.querySelector(o.show.needs);
  return (
    <Modal
      open={open}
      onOpenChange={(e) => !e && s()}
      title={i ? msg("Common questions") : o.title}
      description={
        i
          ? msg("Short answers to what people ask most.")
          : msg("Step {{v0}} of {{v1}}", {
              v0: n + 1,
              v1: TOUR_STEPS.length,
            })
      }
      size="sm"
      footer={
        i ? (
          <Button onClick={() => a(false)}>{msg("Back to the tour")}</Button>
        ) : (
          <>
            <Button variant="ghost" className="mr-auto" onClick={() => a(true)}>
              {msg("Common questions")}
            </Button>
            <Button variant="ghost" disabled={n === 0} onClick={() => r(n - 1)}>
              {msg("Back")}
            </Button>
            {n < TOUR_STEPS.length - 1 ? (
              <Button variant="primary" onClick={() => r(n + 1)}>
                {msg("Next")}
              </Button>
            ) : (
              <Button variant="primary" onClick={s}>
                {msg("Done")}
              </Button>
            )}
          </>
        )
      }
    >
      {i ? (
        <dl className="space-y-2 text-[13px]">
          {FAQ.map((e) => (
            <div key={e.q}>
              <dt className="font-medium">{e.q}</dt>
              <dd className="text-muted">{e.a}</dd>
            </div>
          ))}
        </dl>
      ) : (
        <div className="space-y-3">
          <p className="text-[13px] leading-relaxed text-muted" aria-live="polite">
            {o.body}
          </p>
          {o.show && c && (
            <Button
              size="sm"
              onClick={() => {
                let e = o.show.run;
                (s(), setTimeout(e, 50));
              }}
            >
              {o.show.label}
            </Button>
          )}
          {o.show?.needs && !c && <p className="text-xs text-faint">{msg("Open a story to see this.")}</p>}
        </div>
      )}
    </Modal>
  );
}
