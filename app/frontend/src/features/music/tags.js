// Music tags (v1.8): the vocabulary comes from the server (services/music.py TAGS), labels in English and French.
import { useQuery } from "@tanstack/react-query";
import { apiGet } from "@/api/legacy";
import { shownLanguage } from "@/i18n";

export function useMusicTags() {
  return useQuery({ queryKey: [`music-tags`], queryFn: () => apiGet(`/music/tags`), staleTime: Infinity });
}

/** A tag id shown in the interface language; custom tags are shown as written ("my_tag" -> "my tag"). */
export function tagLabel(data, id) {
  let t = data?.tags?.find((x) => x.id === id);
  return t ? (t.label[shownLanguage()] ?? t.label.en) : String(id).replace(/_/g, ` `);
}

export function groupLabel(data, id) {
  let g = data?.groups?.find((x) => x.id === id);
  return g ? (g.label[shownLanguage()] ?? g.label.en) : id;
}
