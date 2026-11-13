// Reconstructed from the StoryCore v1.7.0 compiled bundle (see DEVONLY/13_FRONTEND_SOURCE.md).
import * as React from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { msg } from "@/i18n";

var QUOTE_PAIRS = {
    "“": `”`,
    "«": `»`,
    "„": `”`,
  },
  CLOSING_QUOTES = new Set([`”`, `»`]),
  isSpaceOrEnd = (e) => e === undefined || /\s/.test(e),
  isOpeningContext = (e) => isSpaceOrEnd(e) || (!!e && `([{—–-*_`.includes(e));

function scanQuotes(e) {
  let t = [],
    n = [],
    r = false;
  for (let i = 0; i < e.length; i++) {
    let a = e[i],
      o = n[n.length - 1];
    a === `"`
      ? o?.close === `"`
        ? (n.pop(),
          n.length ||
            t.push({
              start: o.at,
              end: i + 1,
            }))
        : isOpeningContext(e[i - 1])
          ? n.push({
              close: `"`,
              at: i,
            })
          : n.length || (r = true)
      : QUOTE_PAIRS[a]
        ? n.push({
            close: QUOTE_PAIRS[a],
            at: i,
          })
        : CLOSING_QUOTES.has(a) &&
          (o?.close === a
            ? (n.pop(),
              n.length ||
                t.push({
                  start: o.at,
                  end: i + 1,
                }))
            : n.length || (r = true));
  }
  return {
    spans: t,
    open: n.length ? n[0].at : null,
    stray: r,
  };
}

var WRITTEN_WORD_CONTEXT =
    /(?:\b(?:reads?|reading|wrote|written|writes|titled|entitled|labell?ed|inscribed|engraved|signed|the words?|the phrase|the term|so-called|known as|called|named|intitul[ée]e?s?|nomm[ée]e?s?|appel[ée]e?s?|le mot|les mots|l'inscription|on y lit)\b[\s:,]*)$/iu,
  FP =
    /\b(?:said|says|say|asked|asks|replied|replies|answered|answers|whispered|whispers|murmured|murmurs|shouted|shouts|added|adds|continued|continues|snapped|snaps|muttered|mutters|dit|demande|demanda|répond|répondit|murmure|murmura|souffle|souffla|ajoute|ajouta|lance|lança|crie|cria)\b/iu;

function isLikelyDialogue(e, t, n) {
  let r = e.slice(t.start + 1, t.end - 1).trim();
  if (!r) return false;
  let i = e.slice(t.start, t.end);
  if (n.some((e) => i.includes(e) || e.includes(r))) return true;
  let a = e.slice(Math.max(0, t.start - 32), t.start);
  if (WRITTEN_WORD_CONTEXT.test(a)) return false;
  if (
    r.split(/\s+/).length > 3 ||
    /[.!?…,;:]/.test(r) ||
    (!e.slice(0, t.start).trim() && !e.slice(t.end).replace(/[\s.,!?…]/g, ``))
  )
    return true;
  let o = e.slice(t.end, t.end + 24);
  return FP.test(o) || FP.test(a);
}

function classifyParagraph(e, { verified = [], streaming = false } = {}) {
  if (/^\s*[—–]\s/.test(e))
    return {
      level: `uncertain`,
      spans: [],
    };
  let { spans, open, stray } = scanQuotes(e);
  if (stray || (open !== null && !streaming))
    return {
      level: `uncertain`,
      spans: [],
    };
  let o = spans.filter((n) => isLikelyDialogue(e, n, verified));
  return (
    open !== null &&
      o.push({
        start: open,
        end: e.length,
      }),
    !o.length && !spans.length
      ? {
          level: `narration`,
          spans: [],
        }
      : {
          level: `mixed`,
          spans: o,
        }
  );
}

function textOf(e) {
  let t = ``;
  return (
    React.Children.forEach(e, (e) => {
      typeof e == `string` || typeof e == `number`
        ? (t += String(e))
        : React.isValidElement(e) && (t += textOf(e.props.children));
    }),
    t
  );
}

function highlightSpans(e, t, n) {
  return React.Children.map(e, (e) => {
    if (typeof e == `string` || typeof e == `number`) {
      let r = String(e),
        i = n.at;
      n.at += r.length;
      let a = [],
        o = 0;
      for (let e of t) {
        let t = Math.max(e.start - i, o),
          n = Math.min(e.end - i, r.length);
        n <= t ||
          (t > o && a.push(r.slice(o, t)),
          a.push(
            <span className="story-dialogue" key={i + t}>
              {r.slice(t, n)}
            </span>,
          ),
          (o = n));
      }
      return a.length ? (o < r.length && a.push(r.slice(o)), a) : r;
    }
    return React.isValidElement(e) && e.props.children !== undefined
      ? React.cloneElement(e, undefined, highlightSpans(e.props.children, t, n))
      : e;
  });
}

function findVerified(e, t) {
  let n = [];
  for (let r of t)
    for (let t = e.indexOf(r); t >= 0; t = e.indexOf(r, t + r.length))
      n.push({
        start: t,
        end: t + r.length,
      });
  return n.sort((e, t) => e.start - t.start);
}

function DialogueParagraph({ as: CompE, children, verified, mode, streaming }) {
  let a = textOf(children);
  if (mode === `verified`)
    return (
      <CompE>
        {highlightSpans(children, findVerified(a, verified), {
          at: 0,
        })}
      </CompE>
    );
  let o = classifyParagraph(a, {
    verified,
    streaming,
  });
  return (
    <CompE className={o.level === `uncertain` ? `story-plain` : `story-narration`}>
      {o.spans.length
        ? highlightSpans(children, o.spans, {
            at: 0,
          })
        : children}
    </CompE>
  );
}

export function StoryMarkdown({ text, className, dialogue = [], reading, streaming = false }) {
  let a = dialogue.filter((e) => e.trim().length >= 2);
  return (
    <div className={className}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        skipHtml
        components={{
          a: ({ href, children }) => (
            <a
              href={href}
              target="_blank"
              rel="noreferrer noopener"
              className="text-accent underline underline-offset-2"
            >
              {children}
            </a>
          ),
          img: ({ alt }) => (
            <span className="text-faint">
              {msg("[image:")} {alt}]
            </span>
          ),
          pre: ({ children }) => <pre className="story-pre">{children}</pre>,
          ...(reading
            ? {
                p: ({ children }) => (
                  <DialogueParagraph as="p" verified={a} mode={reading} streaming={streaming}>
                    {children}
                  </DialogueParagraph>
                ),
                li: ({ children }) => (
                  <DialogueParagraph as="li" verified={a} mode={reading} streaming={streaming}>
                    {children}
                  </DialogueParagraph>
                ),
              }
            : {}),
        }}
      >
        {text}
      </ReactMarkdown>
    </div>
  );
}
