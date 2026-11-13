// Reconstructed from the StoryCore v1.7.0 compiled bundle (see DEVONLY/13_FRONTEND_SOURCE.md).
import { useCommands, queryKeys, useStories } from "@/api/queries";
import { useQueryClient } from "@tanstack/react-query";
import * as React from "react";
import { apiGet, apiPost, errorMessage, apiDelete, apiPut } from "@/api/legacy";
import * as Icon from "lucide-react";
import { msg } from "@/i18n";
import { Badge, Button, Field, IconButton, Input, Modal, Select, Textarea, Toggle, useUi } from "@/components/ui";
import { cn, downloadJson, readFileText } from "@/lib/util";

var COMMAND_KIND_TONES = {
  name: ``,
  aliases_json: [],
  description: ``,
  template: `{{input}}`,
  kind: `prompt`,
  action: null,
  output_target: `chat`,
  scope: `global`,
  story_id: null,
  pinned: false,
  category: `Custom`,
  enabled: true,
};

export function CommandsPage() {
  let commands = useCommands(),
    queryClient = useQueryClient(),
    { toast, confirm } = useUi(),
    [i, a] = React.useState(``),
    [o, s] = React.useState(null),
    c = React.useRef(null),
    l = () =>
      queryClient.invalidateQueries({
        queryKey: [`commands`],
      }),
    u = React.useMemo(() => {
      let t = i.toLowerCase(),
        n = (commands.data ?? []).filter(
          (e) =>
            !t ||
            e.name.includes(t) ||
            e.description.toLowerCase().includes(t) ||
            e.aliases_json.some((e) => e.includes(t)),
        ),
        r = {};
      for (let e of n) (r[e.category] ??= []).push(e);
      return Object.entries(r).sort(([e], [t]) => e.localeCompare(t));
    }, [commands.data, i]);
  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-4xl px-6 py-8">
        <div className="mb-4 flex flex-wrap items-center gap-2">
          <h1 className="text-xl font-semibold">{msg("Slash commands")}</h1>
          <div className="ml-auto flex gap-2">
            <Button
              size="sm"
              variant="ghost"
              onClick={async () => downloadJson(`storycore-commands.json`, await apiGet(`/commands/export`))}
            >
              <Icon.Download className="size-3.5" /> {msg("Export")}
            </Button>
            <Button size="sm" variant="ghost" onClick={() => c.current?.click()}>
              <Icon.Upload className="size-3.5" /> {msg("Import")}
            </Button>
            <input
              ref={c}
              type="file"
              accept=".json"
              className="hidden"
              onChange={async (e) => {
                let t = e.target.files?.[0];
                if (t) {
                  try {
                    let e = await apiPost(`/commands/import`, JSON.parse(await readFileText(t)));
                    (l(),
                      toast(
                        msg("Imported {{v0}} command(s){{v1}}", {
                          v0: e.added,
                          v1: e.skipped.length ? `, skipped ${e.skipped.length}` : ``,
                        }),
                      ));
                  } catch (e) {
                    toast(errorMessage(e), `danger`);
                  }
                  e.target.value = ``;
                }
              }}
            />
            <Button
              size="sm"
              variant="primary"
              onClick={() =>
                s({
                  ...COMMAND_KIND_TONES,
                })
              }
            >
              <Icon.Plus className="size-3.5" /> {msg("New command")}
            </Button>
          </div>
        </div>
        <p className="mb-3 text-sm text-muted">
          {msg("Type")} <code className="text-accent">/</code>{" "}
          {msg("in a story to open the palette. Commands are prompt templates or app actions — never shell commands.")}{" "}
          <code>{"{{input}}"}</code> {msg("is replaced by the text you type after the command.")}
        </p>
        <div className="relative mb-4">
          <Icon.Search className="absolute left-2 top-2.5 size-3.5 text-faint" />
          <Input
            value={i}
            onChange={(e) => a(e.target.value)}
            placeholder={msg("Search commands")}
            aria-label={msg("Search commands")}
            className="pl-7"
          />
        </div>
        {u.map(([e, t]) => (
          <section className="mb-5" key={e}>
            <h2 className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-faint">{e}</h2>
            <div className="divide-y divide-line rounded-lg border border-line">
              {t.map((e) => (
                <div className={cn(`flex items-center gap-3 px-3 py-2`, !e.enabled && `opacity-50`)} key={e.id}>
                  <button onClick={() => s(e)} className="min-w-0 flex-1 text-left">
                    <span className="flex flex-wrap items-center gap-1.5">
                      <span className="font-mono text-sm text-accent">/{e.name}</span>
                      {e.aliases_json.map((e) => (
                        <span className="font-mono text-xs text-faint" key={e}>
                          /{e}
                        </span>
                      ))}
                      {e.builtin && <Badge>{msg("built-in")}</Badge>}
                      <Badge tone={e.kind === `prompt` ? `info` : e.kind === `hybrid` ? `accent` : `neutral`}>
                        {e.kind.replace(`_`, ` `)}
                      </Badge>
                      {e.scope === `story` && <Badge tone="warn">{msg("story")}</Badge>}
                      {e.pinned && <Icon.Pin className="size-3 text-accent" />}
                    </span>
                    <span className="block truncate text-xs text-muted">{e.description}</span>
                  </button>
                  <IconButton
                    label={msg("Duplicate")}
                    onClick={async () => {
                      (await apiPost(`/commands/${e.id}/duplicate`), l());
                    }}
                  >
                    <Icon.Copy className="size-3.5" />
                  </IconButton>
                  {e.builtin ? (
                    <IconButton
                      label={msg("Reset to default")}
                      onClick={async () => {
                        (await confirm({
                          title: msg("Reset /{{v0}}?", {
                            v0: e.name,
                          }),
                          body: msg("Restores the default prompt, aliases and scope."),
                        })) && (await apiPost(`/commands/${e.id}/reset`), l());
                      }}
                    >
                      <Icon.RotateCcw className="size-3.5" />
                    </IconButton>
                  ) : (
                    <IconButton
                      label={msg("Delete")}
                      onClick={async () => {
                        (await confirm({
                          title: msg("Delete /{{v0}}?", {
                            v0: e.name,
                          }),
                          danger: true,
                          confirmLabel: msg("Delete"),
                        })) && (await apiDelete(`/commands/${e.id}`), l());
                      }}
                    >
                      <Icon.Trash className="size-3.5" />
                    </IconButton>
                  )}
                </div>
              ))}
            </div>
          </section>
        ))}
        <p className="text-xs text-faint">
          {commands.data?.length ?? 0} {msg("commands.")}
        </p>
      </div>
      {o && (
        <CommandEditor
          c={o}
          onClose={() => s(null)}
          onSaved={() => {
            (l(),
              queryClient.invalidateQueries({
                queryKey: queryKeys.commands(),
              }));
          }}
        />
      )}
    </div>
  );
}

function CommandEditor({ c: e, onClose, onSaved }) {
  let stories = useStories(),
    { toast } = useUi(),
    [a, o] = React.useState({
      ...COMMAND_KIND_TONES,
      ...e,
      aliases: (e.aliases_json ?? []).join(`, `),
    }),
    s = async () => {
      let r = {
        ...a,
        aliases: a.aliases
          .split(/[,\s]+/)
          .map((e) => e.replace(/^\//, ``).trim())
          .filter(Boolean),
      };
      try {
        (e.id ? await apiPut(`/commands/${e.id}`, r) : await apiPost(`/commands`, r),
          onSaved(),
          onClose(),
          toast(msg("Command saved")));
      } catch (e) {
        toast(errorMessage(e), `danger`);
      }
    },
    c = !!e.builtin;
  return (
    <Modal
      open
      onOpenChange={(e) => !e && onClose()}
      size="lg"
      title={
        e.id
          ? msg("Edit /{{v0}}", {
              v0: e.name,
            })
          : msg("New command")
      }
      footer={
        <Button variant="primary" onClick={s}>
          {msg("Save")}
        </Button>
      }
    >
      <div className="space-y-3">
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label={msg("Name (without /)")}>
            <Input
              value={a.name}
              onChange={(e) =>
                o({
                  ...a,
                  name: e.target.value.toLowerCase().replace(/^\//, ``),
                })
              }
            />
          </Field>
          <Field label={msg("Aliases")} hint={msg("comma separated")}>
            <Input
              value={a.aliases}
              onChange={(e) =>
                o({
                  ...a,
                  aliases: e.target.value,
                })
              }
            />
          </Field>
        </div>
        <Field label={msg("Description")}>
          <Input
            value={a.description}
            onChange={(e) =>
              o({
                ...a,
                description: e.target.value,
              })
            }
          />
        </Field>
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label={msg("Type")} hint={c ? msg("Fixed for built-in commands") : undefined}>
            <Select
              value={a.kind}
              disabled={c}
              onChange={(e) =>
                o({
                  ...a,
                  kind: e.target.value,
                })
              }
            >
              <option value="prompt">{msg("Prompt (sent to the model)")}</option>
              {c && <option value="local_action">{msg("App action")}</option>}
              {c && <option value="hybrid">{msg("App tool + model")}</option>}
            </Select>
          </Field>
          <Field label={msg("Result goes to")}>
            <Select
              value={a.output_target}
              onChange={(e) =>
                o({
                  ...a,
                  output_target: e.target.value,
                })
              }
            >
              <option value="chat">{msg("Story (in character)")}</option>
              <option value="ooc">{msg("Out-of-character box")}</option>
              <option value="utility">{msg("Utility panel")}</option>
            </Select>
          </Field>
          <Field label={msg("Category")}>
            <Input
              value={a.category}
              onChange={(e) =>
                o({
                  ...a,
                  category: e.target.value,
                })
              }
            />
          </Field>
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label={msg("Scope")}>
            <Select
              value={a.scope}
              onChange={(e) =>
                o({
                  ...a,
                  scope: e.target.value,
                  story_id: e.target.value === `story` ? (a.story_id ?? stories.data?.[0]?.id ?? null) : null,
                })
              }
            >
              <option value="global">{msg("All stories")}</option>
              <option value="story">{msg("One story")}</option>
            </Select>
          </Field>
          {a.scope === `story` && (
            <Field label={msg("Story")}>
              <Select
                value={a.story_id ?? ``}
                onChange={(e) =>
                  o({
                    ...a,
                    story_id: e.target.value,
                  })
                }
              >
                {stories.data?.map((e) => (
                  <option value={e.id} key={e.id}>
                    {e.title}
                  </option>
                ))}
              </Select>
            </Field>
          )}
        </div>
        {a.kind !== `local_action` && (
          <Field
            label={msg("Prompt template")}
            hint="{{input}} = text typed after the command · {{location}} · {{player_name}}"
          >
            <Textarea
              value={a.template}
              onChange={(e) =>
                o({
                  ...a,
                  template: e.target.value,
                })
              }
              className="min-h-40 font-mono text-xs"
            />
          </Field>
        )}
        <div className="flex gap-6">
          <Toggle
            checked={a.pinned}
            onChange={(e) =>
              o({
                ...a,
                pinned: e,
              })
            }
            label={msg("Pinned (shown first)")}
          />
          <Toggle
            checked={a.enabled}
            onChange={(e) =>
              o({
                ...a,
                enabled: e,
              })
            }
            label={msg("Enabled")}
          />
        </div>
      </div>
    </Modal>
  );
}
