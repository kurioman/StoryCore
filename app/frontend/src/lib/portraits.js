// Portraits of one story world (v0.5): the same character can look different from one world to the next (a teenager in
// one story, an adult in the next), so a portrait is always looked up in the world of the story or screen shown.
import { useQuery } from "@tanstack/react-query";
import { apiGet } from "@/api/legacy";

/** character id -> {name, slots: {expression: asset id}} for one world (no world: a story without a lore pack). */
export function usePortraitMap(worldId) {
  return useQuery({
    queryKey: [`portrait-map`, worldId ?? null],
    queryFn: () =>
      apiGet(worldId ? `/assets/characters?world_id=${encodeURIComponent(worldId)}` : `/assets/characters`).then(
        (data) => Object.fromEntries(data.characters.map((character) => [character.id, character])),
      ),
    staleTime: 6e4,
  });
}

/** The asset id for an expression (1 neutral by default), falling back to the neutral or any portrait. */
export function portraitSlot(character, expression = 1) {
  if (!character) return null;
  return character.slots[String(expression)] ?? character.slots[1] ?? Object.values(character.slots)[0] ?? null;
}
