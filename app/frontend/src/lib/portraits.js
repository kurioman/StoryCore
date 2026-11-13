// Reconstructed from the StoryCore v1.7.0 compiled bundle (see DEVONLY/13_FRONTEND_SOURCE.md).
import { useQuery } from "@tanstack/react-query";
import { apiGet } from "@/api/legacy";

export function usePortraitMap() {
  return useQuery({
    queryKey: [`portrait-map`],
    queryFn: () => apiGet(`/assets/characters`).then((e) => Object.fromEntries(e.characters.map((e) => [e.id, e]))),
    staleTime: 6e4,
  });
}

export function portraitSlot(e, t = 1) {
  return e ? (e.slots[String(t)] ?? e.slots[1] ?? Object.values(e.slots)[0] ?? null) : null;
}
