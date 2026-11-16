// Welcome page logo (v0.5): a star born from an open book. Used ONLY on the welcome page; the rest of the app keeps
// the four-point star (Logo in features/sidebar/Sidebar.jsx, favicon in index.html). "full" adds the page lines and
// the little sparkles; the plain version is for small sizes.
import * as React from "react";

const GOLD = ["#fbe4a3", "#e2bd72", "#b48a43"];

export function BrandLogo({ full = false, className }: { full?: boolean; className?: string }) {
  const id = `sc-logo-${React.useId().replace(/:/g, ``)}`;
  return (
    <svg viewBox={full ? `0 0 120 120` : `10 8 100 100`} className={className} aria-hidden>
      <defs>
        <linearGradient id={id} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor={GOLD[0]} />
          <stop offset="0.5" stopColor={GOLD[1]} />
          <stop offset="1" stopColor={GOLD[2]} />
        </linearGradient>
      </defs>
      <path d="M60 12 L65.5 33.5 L87 39 L65.5 44.5 L60 66 L54.5 44.5 L33 39 L54.5 33.5 Z" fill={`url(#${id})`} />
      <circle cx="60" cy="39" r="3" fill="#0b1030" />
      <path d="M60 104 C48 95 32 92 14 94 L14 70 C32 68 48 70 60 79 Z" fill={`url(#${id})`} />
      <path d="M60 104 C72 95 88 92 106 94 L106 70 C88 68 72 70 60 79 Z" fill={`url(#${id})`} />
      <path d="M60 79 L60 104" stroke="#0b1030" strokeWidth={full ? 2.4 : 4} />
      {full && (
        <>
          <circle cx="33" cy="20" r="2.2" fill="#f6d98f" />
          <circle cx="90" cy="18" r="1.6" fill="#f6d98f" />
          <circle cx="96" cy="54" r="1.4" fill="#f6d98f" />
          <path
            d="M22 78 C34 76 46 78 54 83 M22 85 C34 83 46 85 54 90 M98 78 C86 76 74 78 66 83 M98 85 C86 83 74 85 66 90"
            stroke="#0b1030"
            strokeWidth="1.4"
            fill="none"
            opacity=".55"
          />
        </>
      )}
    </svg>
  );
}
