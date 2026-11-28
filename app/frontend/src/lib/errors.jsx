// v0.7.7 "clear errors": every failure the player can meet, as a short title, one plain sentence and the button that
// helps. The provider's own (English, technical) text stays available under "Technical details".
// Functions, not constants: the texts are translated when shown (the interface language can change without a reload).
import * as React from "react";
import * as Icon from "lucide-react";
import { msg } from "@/i18n";

function texts() {
  return {
    auth: [
      msg("Your API key was refused"),
      msg("The provider does not accept your key. Check that it was pasted in full, or create a new key on the provider's site."),
      `providers`,
    ],
    credits: [
      msg("No credit left"),
      msg("Your account has no credit left or reached its spending limit. Add credit on the provider's site, then retry."),
      `retry`,
    ],
    rate_limit: [msg("Too many requests"), msg("The provider asks you to slow down. Wait a few seconds, then retry."), `retry`],
    not_found: [
      msg("Model not found"),
      msg("This model no longer exists or its name is wrong. Choose another model in the AI settings."),
      `providers`,
    ],
    context_overflow: [
      msg("The story is too long for this model"),
      msg("The request does not fit in the model's memory. Make a recap, lower the context budget in the settings, or choose a model with a bigger context."),
      `retry`,
    ],
    bad_request: [
      msg("The model refused the request"),
      msg("A setting is probably not supported by this model. Retry, or choose another model."),
      `providers`,
    ],
    unavailable: [
      msg("The provider is overloaded"),
      msg("The provider's servers are busy or down. Retry in a moment, or choose another model."),
      `retry`,
    ],
    timeout: [msg("No answer in time"), msg("The model took too long to answer. Retry; if it happens often, choose a faster model."), `retry`],
    network: [
      msg("No connection to the AI"),
      msg("StoryCore could not reach the provider. Check your internet connection (or that LM Studio is running), then retry."),
      `retry`,
    ],
    stream_error: [msg("The reply stopped halfway"), msg("The provider stopped while writing. Retry."), `retry`],
    invalid_response: [
      msg("Unreadable answer"),
      msg("The provider sent an answer StoryCore cannot read. Retry; if it persists, choose another model."),
      `retry`,
    ],
    empty_output: [msg("Empty answer"), msg("The model sent no text. Retry; if it persists, choose another model."), `retry`],
    refusal: [
      msg("Reply blocked by the provider's filter"),
      msg("The provider's content filter stopped this reply. Rephrase your message, or choose another model."),
      `retry`,
    ],
    truncated: [
      msg("Reply cut off"),
      msg("The reply reached the model's length limit. Retry, or raise the maximum reply length in the settings."),
      `retry`,
    ],
    no_story: [
      msg("The model wrote no story"),
      msg("The model answered twice with notes only. Retry; if it happens often, choose another model."),
      `retry`,
    ],
    start_failed: [msg("The reply could not start"), msg("Your message is kept. Retry when you are ready."), `retry`],
    interrupted: [msg("Reply interrupted"), msg("The app stopped while writing. The text received so far is kept."), `retry`],
    internal: [
      msg("Unexpected error"),
      msg("Something went wrong in StoryCore. Retry; if it happens again, use Report a problem."),
      `retry`,
    ],
    budget: [
      msg("Spending cap reached"),
      msg("Nothing was sent and your message is kept. Raise the cap to keep playing."),
      `budget`,
    ],
    no_model: [msg("No model selected"), msg("Choose an AI model in the settings to play."), `providers`],
    consent: [msg("Your permission is needed"), msg("This request would be sent to an online model: allow it first."), null],
  };
}

/** {title, text, action, technical} for an error object ({category, message, details}) or null. */
export function friendlyError(error) {
  if (!error) return null;
  const known = texts()[error.category];
  const technical = [error.message, error.details].filter(Boolean).join(`\n`);
  if (!known) return { title: msg("Something went wrong"), text: error.message || ``, action: `retry`, technical: error.details || `` };
  return { title: known[0], text: known[1], action: known[2], technical };
}

/** The plain-language sentence for a test result {ok, message, error} (settings): the provider's text when it worked. */
export function resultText(result) {
  if (!result) return ``;
  if (result.ok || !result.error) return result.message ?? ``;
  const f = friendlyError(result.error);
  return `${f.title}. ${f.text}`;
}

export function TechnicalDetails({ text, className = `` }) {
  const [open, setOpen] = React.useState(false);
  if (!text) return null;
  return (
    <div className={className}>
      <button type="button" className="inline-flex items-center gap-1 text-[11px] opacity-80 underline-offset-2 hover:underline" onClick={() => setOpen(!open)}>
        <Icon.ChevronRight className={`size-3 transition-transform ${open ? `rotate-90` : ``}`} />
        {msg("Technical details")}
      </button>
      {open && <pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap break-words rounded bg-black/20 p-2 text-[11px]">{text}</pre>}
    </div>
  );
}

/** A test result of the settings ({ok, message, error}): plain text, with the technical text folded when it failed. */
export function ResultText({ result }) {
  if (!result) return null;
  if (result.ok || !result.error) return <>{result.message}</>;
  const f = friendlyError(result.error);
  return (
    <>
      <span className="font-medium">{f.title}.</span> {f.text}
      <TechnicalDetails text={f.technical} className="mt-1" />
    </>
  );
}
