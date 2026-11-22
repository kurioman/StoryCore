// World creator (Phase 8): calls to /api/creator/... (backend: routers/creator.py, services/pack_editor.py).
import { api } from "@/api/client";

function form(file) {
  let f = new FormData();
  f.append(`file`, file);
  return f;
}

export const creatorApi = {
  list: () => api.get(`/creator/worlds`).then((r) => r.worlds),
  create: (name, copyFrom = ``) => api.post(`/creator/worlds`, { name, copy_from: copyFrom }),
  read: (id) => api.get(`/creator/worlds/${id}`),
  save: (id, changes) => api.put(`/creator/worlds/${id}`, changes),
  remove: (id) => api.del(`/creator/worlds/${id}`),
  check: (id) => api.get(`/creator/worlds/${id}/check`),
  assist: (id, kind, idea, lang) => api.post(`/creator/worlds/${id}/assist`, { kind, idea, lang }),
  uploadCover: (id, file) => api.upload(`/creator/worlds/${id}/cover`, form(file)),
  removeCover: (id) => api.del(`/creator/worlds/${id}/cover`),
  uploadPortrait: (id, characterId, n, file) =>
    api.upload(`/creator/worlds/${id}/portraits/${encodeURIComponent(characterId)}/${n}`, form(file)),
  removePortraits: (id, characterId, n = 0) =>
    api.del(`/creator/worlds/${id}/portraits/${encodeURIComponent(characterId)}${n ? `?n=${n}` : ``}`),
  uploadPlaceImage: (id, placeId, file) =>
    api.upload(`/creator/worlds/${id}/places/${encodeURIComponent(placeId)}/image`, form(file)),
  removePlaceImage: (id, placeId) => api.del(`/creator/worlds/${id}/places/${encodeURIComponent(placeId)}/image`),
  importZip: (file) => api.upload(`/creator/import`, form(file)),
  imageUrl: (id, path, version = 0) =>
    `/api/creator/worlds/${id}/image?path=${encodeURIComponent(path)}&v=${version}`,
  exportUrl: (id) => `/api/creator/worlds/${id}/export`,
};

/** An id made from a name ("Mara Vent" -> "mara_vent"), unique among `taken`. Same rule as the backend. */
export function makeId(name, taken = new Set(), fallback = `item`) {
  let base =
    String(name ?? ``)
      .normalize(`NFKD`)
      .replace(/[̀-ͯ]/g, ``)
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, `_`)
      .replace(/^_+|_+$/g, ``)
      .slice(0, 60) || fallback,
    id = base,
    n = 2;
  while (taken.has(id)) id = `${base}_${n++}`;
  return id;
}
