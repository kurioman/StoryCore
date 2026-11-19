// Portraits of one story world (v0.5): the same character can look different from one world to the next (a teenager in
// one story, an adult in the next), so a portrait is always looked up in the world of the story or screen shown.
import React from "react";
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

/** v0.6: loads the six expressions of the characters in the scene ahead of time, so a change of expression (or the
 * portrait shown while a reply is written) appears at once instead of waiting for the image to download. */
export function usePreloadPortraits(worldId, characterIds) {
  const portraits = usePortraitMap(worldId);
  const key = [...new Set((characterIds ?? []).filter(Boolean))].sort().join(`,`);
  React.useEffect(() => {
    if (!portraits.data || !key) return undefined;
    const images = [];
    for (const id of key.split(`,`))
      for (const assetId of Object.values(portraits.data[id]?.slots ?? {}))
        for (const variant of [`full`, `thumb`]) {
          const image = new Image();
          image.decoding = `async`;
          image.src = `/api/assets/${assetId}/image?variant=${variant}`;
          images.push(image);
        }
    return () => {
      images.length = 0;
    };
  }, [portraits.data, key]);
}
