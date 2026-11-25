// Library pieces shared by the library page and the story sheet: a world's cover and its tags.
import { msg, shownLanguage } from "@/i18n";
import { cn } from "@/lib/util";

export function coverUrl(world) {
  return world?.data_json?.library?.cover ? `/api/worlds/${world.id}/cover` : null;
}

export function Cover({ world, className }) {
  let url = coverUrl(world);
  return url ? (
    <img src={url} alt="" className={cn(`object-cover`, className)} draggable={false} />
  ) : (
    <div className={cn(`sc-lib-nocover flex items-center justify-center p-3 text-center`, className)}>
      <span className="sc-brand text-lg text-[#f3dca0]">{world?.name ?? msg("Free-form story")}</span>
    </div>
  );
}

export function Tags({ world, className }) {
  let t = world?.data_json?.library?.tags ?? {},
    tags = t[shownLanguage()] || t.en || t.default || Object.values(t)[0] || [];
  if (!tags.length) return null;
  return (
    <div className={cn(`flex flex-wrap gap-1.5`, className)}>
      {tags.map((t) => (
        <span key={t} className="sc-lib-tag">
          {t}
        </span>
      ))}
    </div>
  );
}
