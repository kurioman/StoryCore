// Reconstructed from the StoryCore v1.7.0 compiled bundle (see DEVONLY/13_FRONTEND_SOURCE.md).
import * as React from "react";
import * as Icon from "lucide-react";
import { msg } from "@/i18n";
import { Badge, Button, Callout, IconButton, Input, SectionTitle, Select, Spinner } from "@/components/ui";
import { ListEditor } from "@/features/story/panels/RelationsPanel";
import { cn } from "@/lib/util";
import { useStateEditor } from "@/features/lore/schemas";

export function ItemsPanel({ storyId }) {
  let stateEditor = useStateEditor(storyId),
    [n, r] = React.useState(``);
  if (!stateEditor.state) return <Spinner />;
  let i = stateEditor.state.inventory,
    a = stateEditor.state.stats.filter((e) => /gold|crown|coin|money|credit/i.test(e.label));
  return (
    <div className="space-y-3">
      {a.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {a.map((e) => (
            <Badge tone="accent" key={e.id}>
              {e.label}
              {": "}
              {String(e.value)} {e.unit}
            </Badge>
          ))}
        </div>
      )}
      {i.length === 0 && <p className="text-xs text-faint">{msg("Inventory is empty.")}</p>}
      {i.map((e) => (
        <div className="group flex items-center gap-2 rounded-md border border-line px-2 py-1.5 text-xs" key={e.id}>
          <button
            title={e.equipped ? msg("Equipped — click to unequip") : msg("Click to equip")}
            onClick={() =>
              stateEditor.save(
                (t) =>
                  void (t.inventory = t.inventory.map((t) =>
                    t.id === e.id
                      ? {
                          ...t,
                          equipped: !t.equipped,
                        }
                      : t,
                  )),
                `${e.equipped ? `Unequipped` : `Equipped`} ${e.name}`,
              )
            }
            className={cn(
              `size-2.5 rounded-full border`,
              e.equipped ? `border-accent bg-accent` : `border-line-strong`,
            )}
            aria-label={msg("Toggle equipped: {{v0}}", {
              v0: e.name,
            })}
          />
          <span className="min-w-0 flex-1 truncate">
            {e.name}
            {e.note && (
              <span className="text-faint">
                {" — "}
                {e.note}
              </span>
            )}
          </span>
          <span className="flex items-center tabular-nums">
            <IconButton
              label={msg("Remove one")}
              className="size-5"
              onClick={() =>
                stateEditor.change.mutate({
                  kind: `inventory_remove`,
                  payload: {
                    name: e.name,
                    qty: 1,
                  },
                })
              }
            >
              <Icon.Minus className="size-3" />
            </IconButton>
            ×{e.qty}
            <IconButton
              label={msg("Add one")}
              className="size-5"
              onClick={() =>
                stateEditor.change.mutate({
                  kind: `inventory_add`,
                  payload: {
                    name: e.name,
                    qty: 1,
                  },
                })
              }
            >
              <Icon.Plus className="size-3" />
            </IconButton>
          </span>
        </div>
      ))}
      <form
        className="flex gap-1"
        onSubmit={(e) => {
          (e.preventDefault(),
            n.trim() &&
              stateEditor.change.mutate({
                kind: `inventory_add`,
                payload: {
                  name: n.trim(),
                  qty: 1,
                },
              }),
            r(``));
        }}
      >
        <Input
          value={n}
          onChange={(e) => r(e.target.value)}
          placeholder={msg("Add item")}
          className="h-7 text-xs"
          aria-label={msg("New item name")}
        />
        <Button size="sm" type="submit">
          {msg("Add")}
        </Button>
      </form>
    </div>
  );
}

export function QuestsPanel({ storyId }) {
  let stateEditor = useStateEditor(storyId),
    [n, r] = React.useState(``);
  if (!stateEditor.state) return <Spinner />;
  let i = stateEditor.state;
  return (
    <div className="space-y-4">
      <section>
        <SectionTitle>{msg("Quests")}</SectionTitle>
        <div className="space-y-2">
          {i.quests.map((e) => (
            <div className="rounded-md border border-line p-2 text-xs" key={e.id}>
              <div className="flex items-center gap-2">
                <span className="min-w-0 flex-1 truncate font-medium">{e.title}</span>
                <Select
                  value={e.status}
                  onChange={(n) =>
                    stateEditor.change.mutate({
                      kind: `quest`,
                      payload: {
                        title: e.title,
                        status: n.target.value,
                      },
                    })
                  }
                  className="h-6 w-28 text-[11px]"
                  aria-label={msg("Quest status")}
                >
                  {[`active`, `completed`, `failed`, `abandoned`].map((e) => (
                    <option key={e}>{e}</option>
                  ))}
                </Select>
              </div>
              <ListEditor
                items={e.objectives.map((e) => ({
                  id: e.id,
                  text: e.text,
                  done: e.done,
                }))}
                placeholder={msg("Add objective")}
                onAdd={(n) =>
                  stateEditor.change.mutate({
                    kind: `quest`,
                    payload: {
                      title: e.title,
                      objective: n,
                    },
                  })
                }
                onToggle={(n) => {
                  let r = e.objectives.find((e) => e.id === n);
                  stateEditor.change.mutate({
                    kind: `quest`,
                    payload: {
                      title: e.title,
                      objective: r.text,
                      objective_done: !r.done,
                    },
                  });
                }}
                onRemove={(n) =>
                  stateEditor.save(
                    (t) =>
                      void (t.quests = t.quests.map((t) =>
                        t.id === e.id
                          ? {
                              ...t,
                              objectives: t.objectives.filter((e) => e.id !== n),
                            }
                          : t,
                      )),
                    `Objective removed`,
                  )
                }
              />
            </div>
          ))}
          <form
            className="flex gap-1"
            onSubmit={(e) => {
              (e.preventDefault(),
                n.trim() &&
                  stateEditor.change.mutate({
                    kind: `quest`,
                    payload: {
                      title: n.trim(),
                    },
                  }),
                r(``));
            }}
          >
            <Input
              value={n}
              onChange={(e) => r(e.target.value)}
              placeholder={msg("New quest")}
              className="h-7 text-xs"
              aria-label={msg("New quest title")}
            />
            <Button size="sm" type="submit">
              {msg("Add")}
            </Button>
          </form>
        </div>
      </section>
      {[
        {
          key: `goals`,
          title: msg("Immediate goals"),
          ph: `Add goal`,
        },
        {
          key: `promises`,
          title: msg("Pending promises"),
          ph: `Add promise`,
        },
        {
          key: `mysteries`,
          title: msg("Unresolved mysteries"),
          ph: `Add mystery`,
        },
        {
          key: `clues`,
          title: msg("Known clues"),
          ph: `Add clue`,
        },
      ].map((e) => (
        <section key={e.key}>
          <SectionTitle>{e.title}</SectionTitle>
          <ListEditor
            items={i[e.key].map((e) => ({
              id: e.id,
              text: e.text,
              done: e.resolved,
            }))}
            placeholder={e.ph}
            onAdd={(n) =>
              stateEditor.change.mutate({
                kind: `list_add`,
                payload: {
                  list: e.key,
                  text: n,
                },
              })
            }
            onToggle={(n) =>
              stateEditor.save(
                (t) =>
                  void (t[e.key] = t[e.key].map((e) =>
                    e.id === n
                      ? {
                          ...e,
                          resolved: !e.resolved,
                        }
                      : e,
                  )),
                `${e.title}: toggled`,
              )
            }
            onRemove={(n) =>
              stateEditor.save((t) => void (t[e.key] = t[e.key].filter((e) => e.id !== n)), `${e.title}: removed entry`)
            }
          />
        </section>
      ))}
      <Callout tone="info">
        {msg("Edits are saved as new state versions; use Undo on the Status tab to revert the last one.")}
      </Callout>
    </div>
  );
}
