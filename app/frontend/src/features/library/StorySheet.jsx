// Story sheet (library): opened by a story card. The whole new-game flow stays in this window (v1.8, user test
// "création de partie"):
//   1. "pick"   — read the summary, choose the opening and who you play (an avatar, or none). With no avatar yet, a
//                 small prompt offers to create one (an avatar is reused from one story to the next) or to play without.
//   2. "title"  — name the game. The world, the opening and the stat sheet come from the pack, so they are not asked
//                 again. A starting location is asked only when the chosen opening allows it (`choose_location: true`
//                 in the pack's starter), and tone / model sit in a closed "Advanced options" block.
//   3. "ready"  — generate the opening scene, or write the first move yourself.
// The older five-step wizard (#/new) stays for free-form stories without a world.
import * as React from "react";
import * as Dialog from "@radix-ui/react-dialog";
import * as Icon from "lucide-react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useAvatars, useProviders, useSettings, queryKeys } from "@/api/queries";
import { apiPost, errorMessage } from "@/api/legacy";
import { msg, packText } from "@/i18n";
import { UploadedImage, useUi } from "@/components/ui";
import { navigate } from "@/lib/router";
import { cn, timeAgo } from "@/lib/util";
import { DEFAULT_PRESET_ID, presetName } from "@/lib/presets";
import { Cover, Tags } from "@/features/library/parts";

const OUTPUT_MEDIUM = `medium (3–4 paragraphs)`,
  MAX_TOKENS = 3e3;

/** The avatar offered first: a favourite, else the most recently changed one. */
function defaultAvatar(list) {
  if (!list?.length) return ``;
  let fav = list.find((a) => a.favourite);
  if (fav) return fav.id;
  return [...list].sort((a, b) => String(b.updated_at ?? ``).localeCompare(String(a.updated_at ?? ``)))[0].id;
}

/**
 * @param world   the lore pack (world) of the card
 * @param games   the games in progress in this world
 * @param initial optional { starter, avatar, step } to reopen the sheet where the player left it (after creating an avatar)
 */
export function StorySheet({ world, games, onClose, initial }) {
  let starters = world.data_json?.starters ?? [],
    avatars = useAvatars(),
    providers = useProviders(),
    settings = useSettings(),
    queryClient = useQueryClient(),
    { toast } = useUi(),
    [step, setStep] = React.useState(initial?.step === `title` ? `title` : `pick`),
    [pick, setPick] = React.useState(
      starters.some((s) => s.id === initial?.starter) ? initial.starter : (starters[0]?.id ?? ``),
    ),
    // null = not chosen yet (the default avatar is used), `` = no avatar
    [avatarId, setAvatarId] = React.useState(initial?.avatar ?? null),
    [askAvatar, setAskAvatar] = React.useState(false),
    [title, setTitle] = React.useState(``),
    [location, setLocation] = React.useState(``),
    [opts, setOpts] = React.useState({
      preset_id: DEFAULT_PRESET_ID,
      model_profile_id: ``,
      tone: ``,
      pacing: ``,
      output_length: OUTPUT_MEDIUM,
    }),
    [created, setCreated] = React.useState(null),
    starter = starters.find((s) => s.id === pick),
    list = avatars.data ?? [],
    chosenAvatar = avatarId === null ? defaultAvatar(list) : avatarId,
    avatar = list.find((a) => a.id === chosenAvatar),
    locations = world.data_json?.locations ?? [],
    canChooseLocation = !!starter?.choose_location,
    create = useMutation({
      mutationFn: () =>
        apiPost(`/stories`, {
          title: title.trim(),
          world_id: world.id,
          starter_id: pick || null,
          starter_blueprint: starter?.blueprint,
          avatar_id: chosenAvatar || null,
          stat_template: `world`, // the pack decides
          starting_location: canChooseLocation ? location : ``,
          starting_time: ``,
          story_note: ``,
          featured_characters: [],
          agency_policy: ``,
          max_tokens: MAX_TOKENS,
          ...opts,
          model_profile_id: opts.model_profile_id || null,
        }),
      onSuccess: (s) => {
        setCreated(s);
        setStep(`ready`);
        queryClient.invalidateQueries({ queryKey: queryKeys.stories });
      },
      onError: (e) => toast(errorMessage(e), `danger`),
    }),
    [starting, setStarting] = React.useState(false),
    // simple first (test report 26 Nov): the game options stay behind a gear button
    [showOpts, setShowOpts] = React.useState(false);

  // a chosen avatar that was deleted meanwhile falls back to the default
  React.useEffect(() => {
    if (avatarId && avatars.data && !avatars.data.some((a) => a.id === avatarId)) setAvatarId(null);
  }, [avatarId, avatars.data]);

  function next() {
    if (!list.length && avatarId === null) return setAskAvatar(true);
    setStep(`title`);
  }

  async function open(generate) {
    if (!created) return;
    if (generate) {
      setStarting(true);
      try {
        await apiPost(`/stories/${created.id}/start`);
      } catch (e) {
        toast(errorMessage(e), `danger`);
      }
    }
    navigate(`/story/${created.id}`);
  }

  function createAvatar() {
    let back = `/library?world=${encodeURIComponent(world.id)}${pick ? `&starter=${encodeURIComponent(pick)}` : ``}`;
    navigate(`/avatars/new?back=${encodeURIComponent(back)}`);
  }

  return (
    <Dialog.Root open onOpenChange={(o) => !o && !create.isPending && !starting && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-[#04061499] backdrop-blur-[2px]" />
        <Dialog.Content
          aria-describedby={undefined}
          className="sc-cx fixed left-1/2 top-1/2 z-50 flex max-h-[92vh] w-[min(96vw,1000px)] -translate-x-1/2 -translate-y-1/2 overflow-hidden rounded-2xl"
        >
          <div className="hidden w-[38%] shrink-0 sm:block">
            <Cover world={world} className="size-full" />
          </div>
          <div className="relative flex min-w-0 flex-1 flex-col overflow-y-auto p-7">
            <div className="flex items-start gap-3">
              <Dialog.Title className="sc-brand text-3xl leading-tight text-[#f3dca0]">{world.name}</Dialog.Title>
              <Dialog.Close asChild>
                <button
                  className="ml-auto rounded-full p-2 text-[#e2bd72b0] hover:bg-[#e2bd721a] hover:text-[#fff0c4]"
                  aria-label={msg("Close")}
                >
                  <Icon.X className="size-5" />
                </button>
              </Dialog.Close>
            </div>
            <Steps step={step} />

            {step === `pick` && (
              <>
                <Tags world={world} className="mt-4" />
                <p className="mt-4 text-sm leading-relaxed text-[#ece6d8e6]">
                  {packText(world.data_json?.library?.summary, world.description)}
                </p>

                {starters.length > 0 && (
                  <div className="mt-6">
                    <p className="sc-lib-h3">{msg("Choose your opening")}</p>
                    <div className="space-y-2">
                      {starters.map((s) => (
                        <button
                          key={s.id}
                          onClick={() => setPick(s.id)}
                          className={cn(`sc-lib-opening`, pick === s.id && `sc-lib-opening-on`)}
                        >
                          <span className="sc-lib-radio" aria-hidden />
                          <span className="min-w-0 flex-1 text-left">
                            <span className="block text-sm font-semibold text-[#f3dca0]">{packText(s.i18n?.name, s.name)}</span>
                            <span className="mt-0.5 block text-xs leading-relaxed text-[#ece6d8b3]">
                              {packText(s.i18n?.purpose, s.purpose)}
                            </span>
                          </span>
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                {list.length > 0 && (
                  <div className="mt-6">
                    <p className="sc-lib-h3">{msg("Play as")}</p>
                    <div className="flex flex-wrap gap-2">
                      {list.map((a) => (
                        <button
                          key={a.id}
                          onClick={() => setAvatarId(a.id)}
                          className={cn(`sc-ns-avatar`, chosenAvatar === a.id && `sc-ns-avatar-on`)}
                        >
                          <UploadedImage path={a.portrait_path} name={a.name} className="size-9 shrink-0 rounded-full" />
                          <span className="min-w-0 truncate text-sm text-[#f3dca0]">{a.name}</span>
                        </button>
                      ))}
                      <button
                        onClick={() => setAvatarId(``)}
                        className={cn(`sc-ns-avatar`, chosenAvatar === `` && `sc-ns-avatar-on`)}
                      >
                        <span className="flex size-9 shrink-0 items-center justify-center rounded-full border border-dashed border-[#e2bd7266] text-[#e2bd72aa]">
                          <Icon.UserX className="size-4" />
                        </span>
                        <span className="text-sm text-[#ece6d8cc]">{msg("No avatar")}</span>
                      </button>
                      <button onClick={createAvatar} className="sc-ns-avatar">
                        <span className="flex size-9 shrink-0 items-center justify-center rounded-full border border-dashed border-[#e2bd7266] text-[#e2bd72]">
                          <Icon.Plus className="size-4" />
                        </span>
                        <span className="text-sm text-[#ece6d8cc]">{msg("New avatar")}</span>
                      </button>
                    </div>
                  </div>
                )}

                <button className="sc-lib-cta mt-7 self-start px-6 py-2.5 text-base" onClick={next}>
                  <Icon.Sparkles className="size-4" /> {msg("New game")}
                </button>

                {games.length > 0 && (
                  <div className="mt-8">
                    <p className="sc-lib-h3">{msg("Your games in this world")}</p>
                    <div className="space-y-1.5">
                      {games.map((g) => (
                        <button key={g.id} onClick={() => navigate(`/story/${g.id}`)} className="sc-lib-game">
                          <Icon.BookOpen className="size-4 shrink-0 text-[#e2bd72]" />
                          <span className="min-w-0 flex-1 truncate text-left text-sm text-[#ece6d8]">{g.title}</span>
                          <span className="shrink-0 text-xs text-[#e2bd7299]">{g.last_activity ? timeAgo(g.last_activity) : ``}</span>
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </>
            )}

            {step === `title` && (
              <form
                className="mt-6 flex flex-1 flex-col"
                onSubmit={(e) => {
                  e.preventDefault();
                  title.trim() && create.mutate();
                }}
              >
                <div className="flex flex-wrap gap-2 text-xs">
                  {starter && (
                    <span className="sc-ns-chip">
                      <Icon.Flag className="size-3.5" /> {packText(starter.i18n?.name, starter.name)}
                    </span>
                  )}
                  <span className="sc-ns-chip">
                    <Icon.User className="size-3.5" /> {avatar ? avatar.name : msg("No avatar")}
                  </span>
                </div>

                <label htmlFor="ns-title" className="sc-lib-h3 mt-6 block">
                  {msg("Name your game")}
                </label>
                <input
                  id="ns-title"
                  autoFocus
                  className="sc-ns-input text-lg"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder={msg("e.g. The Commoner's Gambit")}
                  maxLength={200}
                />

                {canChooseLocation && locations.length > 0 && (
                  <>
                    <label htmlFor="ns-location" className="sc-lib-h3 mt-6 block">
                      {msg("Starting location")}
                    </label>
                    <select id="ns-location" className="sc-ns-input" value={location} onChange={(e) => setLocation(e.target.value)}>
                      <option value="">{msg("Let the narrator choose")}</option>
                      {locations.map((l) => (
                        <option key={l.id ?? l.name}>{l.name}</option>
                      ))}
                    </select>
                  </>
                )}

                {showOpts && (
                <div className="sc-ns-details mt-6">
                  <p className="sc-lib-h3">{msg("Advanced options")}</p>
                  <div className="mt-3 grid gap-3 sm:grid-cols-2">
                    <Opt label={msg("Narration preset")}>
                      <select className="sc-ns-input" value={opts.preset_id} onChange={(e) => setOpts({ ...opts, preset_id: e.target.value })}>
                        {settings.data?.narration_presets.map((p) => (
                          <option value={p.id} key={p.id}>
                            {presetName(p)}
                          </option>
                        ))}
                      </select>
                    </Opt>
                    <Opt label={msg("Model")}>
                      <select
                        className="sc-ns-input"
                        value={opts.model_profile_id}
                        onChange={(e) => setOpts({ ...opts, model_profile_id: e.target.value })}
                      >
                        <option value="">{msg("Global default")}</option>
                        {providers.data?.profiles.map((m) => {
                          let p = providers.data.providers.find((p) => p.id === m.provider_id);
                          return (
                            <option value={m.id} key={m.id}>
                              {m.display_name} — {p?.display_name}
                            </option>
                          );
                        })}
                      </select>
                    </Opt>
                    <Opt label={msg("Tone")}>
                      <input
                        className="sc-ns-input"
                        value={opts.tone}
                        onChange={(e) => setOpts({ ...opts, tone: e.target.value })}
                        placeholder={msg("e.g. hopeful with real danger")}
                      />
                    </Opt>
                    <Opt label={msg("Pacing")}>
                      <select className="sc-ns-input" value={opts.pacing} onChange={(e) => setOpts({ ...opts, pacing: e.target.value })}>
                        <option value="">{msg("Narrator decides")}</option>
                        <option value="slow-burn, let scenes breathe">{msg("Slow-burn")}</option>
                        <option value="steady">{msg("Steady")}</option>
                        <option value="brisk, keep momentum">{msg("Brisk")}</option>
                      </select>
                    </Opt>
                    <Opt label={msg("Output length")}>
                      <select
                        className="sc-ns-input"
                        value={opts.output_length}
                        onChange={(e) => setOpts({ ...opts, output_length: e.target.value })}
                      >
                        <option value="">{msg("Model default")}</option>
                        <option value="short (1–2 paragraphs)">{msg("Short")}</option>
                        <option value={OUTPUT_MEDIUM}>{msg("Medium")}</option>
                        <option value="long (5–7 paragraphs)">{msg("Long")}</option>
                      </select>
                    </Opt>
                  </div>
                </div>
                )}

                <div className="mt-auto flex items-center gap-3 pt-8">
                  <button type="button" className="sc-su-ghost" onClick={() => setStep(`pick`)} disabled={create.isPending}>
                    <Icon.ArrowLeft className="size-4" /> {msg("Back")}
                  </button>
                  <button
                    type="button"
                    onClick={() => setShowOpts(!showOpts)}
                    aria-label={msg("Advanced options")}
                    aria-pressed={showOpts}
                    title={msg("Advanced options")}
                    className={cn(
                      `flex size-10 items-center justify-center rounded-full border text-[#e2bd72]`,
                      showOpts ? `border-[#e2bd72] bg-[#e2bd7218]` : `border-[#e2bd7244]`,
                    )}
                  >
                    <Icon.Settings className="size-5" />
                  </button>
                  <button
                    type="submit"
                    className="sc-lib-cta ml-auto px-6 py-2.5 text-base disabled:cursor-not-allowed disabled:opacity-50"
                    disabled={!title.trim() || create.isPending}
                  >
                    {create.isPending ? <Icon.Loader2 className="size-4 animate-spin" /> : <Icon.Check className="size-4" />}{" "}
                    {msg("Create the game")}
                  </button>
                </div>
              </form>
            )}

            {step === `ready` && created && (
              <div className="mt-8 flex flex-1 flex-col items-center justify-center text-center">
                <Icon.Sparkles className="size-10 text-[#f3d48c]" />
                <p className="sc-brand mt-3 text-2xl text-[#f3dca0]">{msg("“{{v0}}” is ready", { v0: created.title })}</p>
                <p className="mt-2 max-w-md text-sm text-[#ece6d8b3]">
                  {msg("The AI can write the opening scene for you, or you can write the first move yourself.")}
                </p>
                <button className="sc-lib-cta mt-7 px-7 py-3 text-base" onClick={() => open(true)} disabled={starting}>
                  {starting ? <Icon.Loader2 className="size-4 animate-spin" /> : <Icon.Play className="size-4" />}{" "}
                  {msg("Generate the opening scene")}
                </button>
                <button className="sc-su-ghost mt-3" onClick={() => open(false)} disabled={starting}>
                  <Icon.PenLine className="size-4" /> {msg("I'll write the first move myself")}
                </button>
              </div>
            )}

            {askAvatar && (
              <div className="absolute inset-0 z-10 flex items-center justify-center bg-[#060a1fcc] p-6 backdrop-blur-[2px]">
                <div role="alertdialog" aria-labelledby="ns-ask-title" className="sc-cx w-full max-w-md rounded-2xl p-6 text-center">
                  <Icon.UserRoundPlus className="mx-auto size-10 text-[#e2bd72]" />
                  <p id="ns-ask-title" className="sc-brand mt-3 text-xl text-[#f3dca0]">
                    {msg("Create your avatar?")}
                  </p>
                  <p className="mt-2 text-sm leading-relaxed text-[#ece6d8cc]">
                    {msg("The character you play, reused from one story to the next.")}
                  </p>
                  <button className="sc-lib-cta mt-6 w-full justify-center px-6 py-2.5" onClick={createAvatar}>
                    <Icon.UserRoundPlus className="size-4" /> {msg("Create my avatar")}
                  </button>
                  <button
                    className="sc-su-ghost mt-2 w-full justify-center"
                    onClick={() => {
                      setAvatarId(``);
                      setAskAvatar(false);
                      setStep(`title`);
                    }}
                  >
                    {msg("Play without an avatar")}
                  </button>
                </div>
              </div>
            )}
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function Steps({ step }) {
  let all = [
      [`pick`, msg("Opening")],
      [`title`, msg("Title")],
      [`ready`, msg("Begin")],
    ],
    at = all.findIndex(([k]) => k === step);
  return (
    <ol className="mt-3 flex items-center gap-2 text-xs" aria-label={msg("Steps")}>
      {all.map(([k, label], i) => (
        <li key={k} className="flex items-center gap-2">
          {i > 0 && <span className="h-px w-5 bg-[#e2bd7240]" aria-hidden />}
          <span className={cn(`sc-ns-step`, i === at && `sc-ns-step-on`, i < at && `sc-ns-step-done`)} aria-current={i === at ? `step` : undefined}>
            {i < at ? <Icon.Check className="size-3" /> : i + 1}
          </span>
          <span className={i === at ? `text-[#f3dca0]` : `text-[#e2bd7280]`}>{label}</span>
        </li>
      ))}
    </ol>
  );
}

function Opt({ label, children }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs text-[#e2bd72b0]">{label}</span>
      {children}
    </label>
  );
}
