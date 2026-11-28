// World creator: what each kind of card contains. Functions, not constants: labels are translated when shown
// (the interface language can change without a reload).
import { msg } from "@/i18n";

const MONTHS = [`January`, `February`, `March`, `April`, `May`, `June`, `July`, `August`, `September`, `October`,
  `November`, `December`];

function secrets() {
  return {
    key: `hidden`,
    label: msg("Secrets (narrator only)"),
    type: `lines`,
    hint: msg("One secret per line. The narrator knows them and lets them shape the story, but never says them outright. The player never sees them. Start a line with (Known by: Name, Name) so that only these characters know it."),
  };
}

/** Every list of cards of the creator: the key of its name, its fields, the AI kind and the empty card. */
export function cardKinds() {
  return {
    characters: {
      nameKey: `name`,
      ai: `character`,
      add: msg("Add a character"),
      empty: msg("No character yet. Add the people the player will meet."),
      subtitle: (c) => [c.type, c.affiliation].filter(Boolean).join(` · `),
      fields: [
        { key: `name`, label: msg("Name"), type: `text` },
        { key: `gender`, label: msg("Gender"), type: `text`, placeholder: msg("female, male…") },
        { key: `type`, label: msg("Role"), type: `text`, placeholder: msg("Captain, student, innkeeper…") },
        { key: `race`, label: msg("Species or origin"), type: `text` },
        { key: `title`, label: msg("Title"), type: `text` },
        { key: `affiliation`, label: msg("Group or family"), type: `text` },
        { key: `aliases`, label: msg("Other names"), type: `list`, hint: msg("Separated by commas.") },
        { key: `appearance`, label: msg("Appearance"), type: `textarea` },
        { key: `personality_traits`, label: msg("Personality"), type: `list`, hint: msg("A few words, separated by commas.") },
        { key: `speech`, label: msg("Way of speaking"), type: `text` },
        { key: `notes`, label: msg("Who they are"), type: `textarea` },
        { key: `background`, label: msg("Past"), type: `textarea` },
        { key: `goals`, label: msg("What they want"), type: `textarea`, rows: 2 },
        secrets(),
      ],
    },
    locations: {
      nameKey: `name`,
      ai: `location`,
      add: msg("Add a place"),
      empty: msg("No place yet. Add the cities, buildings and landscapes of your world."),
      subtitle: (l) => [l.type, l.location].filter(Boolean).join(` · `),
      fields: [
        { key: `name`, label: msg("Name"), type: `text` },
        { key: `type`, label: msg("Kind of place"), type: `text`, placeholder: msg("City, tavern, forest, spaceship…") },
        { key: `location`, label: msg("Inside which larger place?"), type: `text` },
        { key: `description`, label: msg("Description"), type: `textarea`, rows: 5 },
        secrets(),
      ],
    },
    groups: {
      nameKey: `name`,
      ai: `group`,
      add: msg("Add a group"),
      empty: msg("No group yet. Add the nations, guilds, families or gangs of your world."),
      subtitle: (g) => g.type ?? ``,
      fields: [
        { key: `name`, label: msg("Name"), type: `text` },
        { key: `type`, label: msg("Kind of group"), type: `text`, placeholder: msg("Guild, family, nation, gang…") },
        { key: `description`, label: msg("Description"), type: `textarea`, rows: 4 },
        { key: `goals`, label: msg("What the group wants"), type: `textarea`, rows: 2 },
        { key: `key_members`, label: msg("Members"), type: `characters` },
        secrets(),
      ],
    },
    glossary: {
      nameKey: `term`,
      add: msg("Add a word"),
      empty: msg("No word yet. Explain the words that only exist in your world (a currency, a magic, a title…)."),
      subtitle: (t) => t.definition ?? ``,
      fields: [
        { key: `term`, label: msg("Word"), type: `text` },
        { key: `definition`, label: msg("Meaning"), type: `textarea`, rows: 4 },
      ],
    },
    starters: {
      nameKey: `name`,
      ai: `starter`,
      add: msg("Add a beginning"),
      empty: msg("No beginning yet. Without one, the narrator improvises the first scene."),
      subtitle: (s) => s.purpose ?? ``,
      fields: [
        { key: `name`, label: msg("Title"), type: `text` },
        { key: `purpose`, label: msg("Short description for the player"), type: `textarea`, rows: 2 },
        {
          key: `blueprint`,
          label: msg("Instructions for the narrator"),
          type: `textarea`,
          rows: 7,
          hint: msg("Where and when it starts, who is there, what happens, and one first choice for the player. Never decide what the player's character does."),
        },
        { key: `scene.location`, label: msg("Starting place"), type: `text` },
        { key: `scene.time`, label: msg("Starting time"), type: `text`, placeholder: `09:00` },
        { key: `scene.present`, label: msg("Characters present at the start"), type: `characters` },
      ],
    },
    stats: {
      nameKey: `label`,
      add: msg("Add a stat"),
      empty: msg("No stat: the player's sheet stays empty."),
      subtitle: (s) => statText(s),
      fields: [
        { key: `label`, label: msg("Name"), type: `text`, placeholder: msg("HP, Mana, Gold, Reputation…") },
        {
          key: `type`,
          label: msg("Kind"),
          type: `select`,
          options: [
            { value: `current_max`, label: msg("Gauge (current / maximum)") },
            { value: `number`, label: msg("Number") },
            { value: `text`, label: msg("Text") },
          ],
        },
        { key: `value`, label: msg("Starting value"), type: `stat_value` },
        { key: `max`, label: msg("Maximum"), type: `number`, when: (s) => s.type === `current_max` },
        { key: `unit`, label: msg("Unit"), type: `text`, placeholder: `g`, when: (s) => s.type === `number` },
      ],
    },
    posts: {
      nameKey: `title`,
      add: msg("Add a unique post"),
      empty: msg("No unique post. Example: the king, the guild master. The narrator never invents a second holder."),
      subtitle: (p) => p.character ?? ``,
      fields: [
        { key: `title`, label: msg("Post"), type: `text`, placeholder: msg("King of the realm") },
        { key: `character`, label: msg("Held by"), type: `character` },
        { key: `aliases`, label: msg("Other words for this post"), type: `list`, hint: msg("Separated by commas.") },
        { key: `note`, label: msg("Note"), type: `text` },
      ],
    },
    closed_groups: {
      nameKey: `title`,
      add: msg("Add a closed group"),
      empty: msg("No closed group. Example: the seven gods. The narrator never adds a member."),
      subtitle: (g) => (g.members ?? []).join(`, `),
      fields: [
        { key: `title`, label: msg("Name"), type: `text` },
        { key: `members`, label: msg("Members"), type: `characters` },
        { key: `types`, label: msg("Every character of these roles"), type: `list`, hint: msg("Separated by commas.") },
      ],
    },
    facts: {
      nameKey: `subject`,
      add: msg("Add a fixed fact"),
      empty: msg("No fixed fact. Example: who is whose sister. The narrator never contradicts them."),
      subtitle: (f) => [f.kind, f.object || f.family || f.text].filter(Boolean).join(` · `),
      fields: [
        {
          key: `kind`,
          label: msg("Kind"),
          type: `select`,
          options: [
            { value: `parent_of`, label: msg("is the parent of") },
            { value: `sibling_of`, label: msg("is the brother or sister of") },
            { value: `spouse_of`, label: msg("is married to") },
            { value: `aunt_of`, label: msg("is the aunt or uncle of") },
            { value: `family_branch`, label: msg("belongs to the family") },
            { value: `other`, label: msg("other fact") },
          ],
        },
        { key: `subject`, label: msg("Character"), type: `character` },
        { key: `object`, label: msg("Other character"), type: `character`, when: (f) => f.kind !== `family_branch` },
        { key: `family`, label: msg("Family"), type: `text`, when: (f) => f.kind === `family_branch` },
        { key: `branch`, label: msg("Branch"), type: `text`, when: (f) => f.kind === `family_branch` },
        { key: `text`, label: msg("The fact"), type: `textarea`, rows: 2, when: (f) => f.kind === `other` },
      ],
      blank: () => ({ kind: `parent_of` }),
    },
    gatherings: {
      nameKey: `name`,
      add: msg("Add a gathering"),
      empty: msg("No gathering. Example: a class, a war council. When the scene matches its words, its members are there."),
      subtitle: (g) => (g.keywords ?? []).join(`, `),
      fields: [
        { key: `name`, label: msg("Name"), type: `text` },
        { key: `keywords`, label: msg("Words that call it"), type: `list`, hint: msg("Separated by commas.") },
        { key: `leader`, label: msg("Leader"), type: `character` },
        { key: `members`, label: msg("Members"), type: `characters` },
        { key: `note`, label: msg("Note"), type: `text` },
      ],
    },
    // v0.6 planned events and the player choices they depend on (services/story_events.py)
    choices: {
      nameKey: `name`,
      add: msg("Add a choice"),
      empty: msg("No choice. Example: the academy wing the player joins. Events can depend on it."),
      subtitle: (c) => (c.options ?? []).map((o) => o.name).filter(Boolean).join(` / `),
      fields: [
        { key: `name`, label: msg("What the player chooses"), type: `text`, placeholder: msg("Academy wing, faction, class…") },
        {
          key: `options`,
          label: msg("Options"),
          type: `options`,
          hint: msg("For each option, the words that show the player chose it, separated by commas. The narrator can also mark the choice itself."),
        },
      ],
    },
    events: {
      nameKey: `title`,
      ai: `event`,
      add: msg("Add an event"),
      empty: msg("No event yet. Events are scenes you decide in advance; the narrator plays them its own way."),
      subtitle: (e) => e.brief ?? ``,
      fields: [
        { key: `title`, label: msg("Title"), type: `text` },
        {
          key: `brief`,
          label: msg("What must happen (for the narrator)"),
          type: `textarea`,
          rows: 5,
          hint: msg("The situation, who is there, what is at stake. Not how the player reacts: the narrator decides how the scene unfolds."),
        },
        { key: `characters`, label: msg("Characters involved"), type: `characters` },
        { key: `after`, label: msg("After these events"), type: `events` },
        { key: `from_turn`, label: msg("Not before the player's turn number"), type: `number` },
        { key: `delay_turns`, label: msg("Turns to wait after the events above"), type: `number` },
        {
          key: `from_date.month`,
          label: msg("Not before this date (month)"),
          type: `select`,
          options: [{ value: ``, label: msg("(any date)") }, ...monthOptions()],
        },
        { key: `from_date.day`, label: msg("Day of the month"), type: `number`, when: (e) => !!e.from_date?.month },
        { key: `needs_choice`, label: msg("Waits for this choice of the player"), type: `choice` },
        { key: `skip_if_choice`, label: msg("Skipped if the player already made this choice"), type: `choice` },
        { key: `variants`, label: msg("What changes with each option"), type: `variants` },
        { key: `firm_after`, label: msg("Reminders before insisting"), type: `number`, hint: msg("2 when empty.") },
        { key: `give_up_after`, label: msg("Reminders before giving up"), type: `number`, hint: msg("6 when empty.") },
      ],
    },
    places: {
      nameKey: `title`,
      add: msg("Add a meeting place"),
      empty: msg("No meeting place. Example: the tavern where the mercenaries drink."),
      subtitle: (p) => (p.keywords ?? []).join(`, `),
      fields: [
        { key: `title`, label: msg("Name"), type: `text` },
        { key: `keywords`, label: msg("Words that name this place"), type: `list`, hint: msg("Separated by commas.") },
        { key: `regulars`, label: msg("Regulars"), type: `characters` },
      ],
    },
  };
}

export function statText(s) {
  if (s.type === `current_max`) return `${s.value ?? 0} / ${s.max ?? s.value ?? 0}`;
  return `${s.value ?? ``}${s.unit ? ` ${s.unit}` : ``}`;
}

export function monthOptions() {
  return MONTHS.map((m) => ({ value: m, label: msg(m) }));
}

/** Read and write a dotted key ("scene.location"). Empty values are removed. */
export function getPath(item, key) {
  return key.split(`.`).reduce((v, k) => (v == null ? undefined : v[k]), item);
}

export function setPath(item, key, value) {
  let [head, ...rest] = key.split(`.`);
  if (!rest.length) {
    let out = { ...item };
    if (value === `` || value == null || (Array.isArray(value) && !value.length)) delete out[head];
    else out[head] = value;
    return out;
  }
  let inner = setPath(item[head] ?? {}, rest.join(`.`), value),
    out = { ...item };
  if (Object.keys(inner).length) out[head] = inner;
  else delete out[head];
  return out;
}
