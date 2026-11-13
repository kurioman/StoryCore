// Reconstructed from the StoryCore v1.7.0 compiled bundle (see DEVONLY/13_FRONTEND_SOURCE.md).
import * as React from "react";
import * as Icon from "lucide-react";
import * as Dialog from "@radix-ui/react-dialog";
import * as PopoverPrimitive from "@radix-ui/react-popover";
import * as TabsPrimitive from "@radix-ui/react-tabs";
import { msg } from "@/i18n";
import { cn } from "@/lib/util";

export var BUTTON_VARIANTS = {
    primary: `bg-accent text-accent-fg hover:brightness-110 border border-transparent font-medium`,
    secondary: `bg-raised text-fg border border-line hover:border-line-strong`,
    ghost: `text-muted hover:text-fg hover:bg-panel-2 border border-transparent`,
    danger: `bg-danger-soft text-danger border border-transparent hover:border-danger/40`,
    subtle: `bg-panel-2 text-fg border border-line hover:bg-raised`,
  },
  Button = React.forwardRef(function (
    { variant = `secondary`, size = `md`, loading, className, children, disabled, ...o },
    s,
  ) {
    return (
      <button
        ref={s}
        disabled={disabled || loading}
        className={cn(
          `inline-flex items-center justify-center gap-1.5 rounded-md transition-colors disabled:opacity-50 disabled:pointer-events-none whitespace-nowrap`,
          size === `sm` ? `h-7 px-2.5 text-[13px]` : `h-8.5 px-3 text-sm`,
          BUTTON_VARIANTS[variant],
          className,
        )}
        {...o}
      >
        {loading && <Icon.LoaderCircle className="size-3.5 animate-spin" aria-hidden />}
        {children}
      </button>
    );
  }),
  IconButton = React.forwardRef(function ({ label, active, className, children, ...i }, a) {
    return (
      <button
        ref={a}
        aria-label={label}
        title={label}
        className={cn(
          `inline-flex size-7 items-center justify-center rounded-md text-muted hover:bg-panel-2 hover:text-fg transition-colors disabled:opacity-40`,
          active && `bg-accent-soft text-accent`,
          className,
        )}
        {...i}
      >
        {children}
      </button>
    );
  }),
  FIELD_CLASS = `rounded-md border border-line bg-panel-2 px-2.5 text-sm text-fg placeholder:text-faint focus:border-accent/60 focus:outline-none disabled:opacity-60`,
  fieldWidth = (e) => (/(^|\s)(w-|flex-1)/.test(e ?? ``) ? `` : `w-full`),
  Input = React.forwardRef(function ({ className, ...t }, n) {
    return <input ref={n} className={cn(FIELD_CLASS, fieldWidth(className), `h-8.5`, className)} {...t} />;
  }),
  Textarea = React.forwardRef(function ({ className, ...t }, n) {
    return (
      <textarea
        ref={n}
        className={cn(FIELD_CLASS, fieldWidth(className), `py-2 leading-relaxed resize-y min-h-20`, className)}
        {...t}
      />
    );
  });

export function Select({ className, children, ...n }) {
  return (
    <select className={cn(FIELD_CLASS, fieldWidth(className), `h-8.5 pr-7`, className)} {...n}>
      {children}
    </select>
  );
}

export function Field({ label, hint, children, className, htmlFor }) {
  let a = React.useId(),
    o = React.isValidElement(children) && typeof children.type != `symbol` ? children : null,
    s = htmlFor ?? o?.props.id ?? a,
    c =
      o && !o.props.id
        ? React.cloneElement(o, {
            id: s,
          })
        : children;
  return (
    <div className={cn(`flex flex-col gap-1`, className)}>
      <label htmlFor={o ? s : htmlFor} className="text-xs font-medium text-muted">
        {label}
      </label>
      {c}
      {hint && <p className="text-xs text-faint">{hint}</p>}
    </div>
  );
}

export function Toggle({ checked, onChange, label, description, disabled }) {
  return (
    <label
      className={cn(
        `flex items-start gap-2.5 cursor-pointer select-none`,
        disabled && `opacity-50 pointer-events-none`,
      )}
    >
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        onClick={() => onChange(!checked)}
        className={cn(
          `mt-0.5 relative h-4.5 w-8 shrink-0 rounded-full transition-colors`,
          checked ? `bg-accent` : `bg-line-strong`,
        )}
      >
        <span
          className={cn(
            `absolute top-0.5 size-3.5 rounded-full bg-white transition-all`,
            checked ? `left-4` : `left-0.5`,
          )}
        />
      </button>
      <span className="flex flex-col">
        <span className="text-sm">{label}</span>
        {description && <span className="text-xs text-faint">{description}</span>}
      </span>
    </label>
  );
}

var TONES = {
  neutral: `bg-panel-2 text-muted border-line`,
  accent: `bg-accent-soft text-accent border-transparent`,
  ok: `bg-ok-soft text-ok border-transparent`,
  warn: `bg-warn-soft text-warn border-transparent`,
  danger: `bg-danger-soft text-danger border-transparent`,
  info: `bg-info-soft text-info border-transparent`,
};

export function Badge({ tone = `neutral`, children, className, title }) {
  return (
    <span
      title={title}
      className={cn(
        `inline-flex items-center gap-1 rounded border px-1.5 py-px text-[11px] font-medium leading-4 whitespace-nowrap`,
        TONES[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

export function Spinner({ className }) {
  return <Icon.LoaderCircle className={cn(`size-4 animate-spin text-muted`, className)} aria-label={msg("Loading")} />;
}

export function EmptyState({ icon, title, children }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-10 text-center text-muted">
      {icon && <div className="text-faint">{icon}</div>}
      <p className="text-sm font-medium text-fg/80">{title}</p>
      {children && <div className="text-xs max-w-sm">{children}</div>}
    </div>
  );
}

export function Callout({ tone = `info`, children, title, className }) {
  let CompI = tone === `ok` ? Icon.CircleCheck : tone === `info` ? Icon.Info : Icon.TriangleAlert;
  return (
    <div
      className={cn(`flex gap-2 rounded-md border px-3 py-2 text-[13px]`, TONES[tone], `border-current/20`, className)}
      role={tone === `danger` ? `alert` : undefined}
    >
      <CompI className="mt-0.5 size-4 shrink-0" aria-hidden />
      <div className="min-w-0 text-fg/90">
        {title && <p className="font-medium text-fg">{title}</p>}
        {children}
      </div>
    </div>
  );
}

export function ErrorCallout({ error: e, onRetry }) {
  let [n, r] = React.useState(false),
    i = e,
    a = i?.data?.error?.details;
  return (
    <Callout tone="danger">
      <p>{i?.message ?? String(e)}</p>
      <div className="mt-1 flex gap-2">
        {onRetry && (
          <button className="text-xs underline" onClick={onRetry}>
            {msg("Retry")}
          </button>
        )}
        {a && (
          <button className="text-xs underline" onClick={() => r(!n)}>
            {n ? msg("Hide") : msg("Show")} {msg("technical details")}
          </button>
        )}
      </div>
      {n && a && <pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap text-[11px] text-muted">{a}</pre>}
    </Callout>
  );
}

export function SectionTitle({ children, action }) {
  return (
    <div className="mb-2 flex items-center justify-between gap-2">
      <h3 className="text-[11px] font-semibold uppercase tracking-wider text-faint">{children}</h3>
      {action}
    </div>
  );
}

export function Kbd({ children }) {
  return <kbd className="rounded border border-line bg-panel-2 px-1 font-mono text-[10px] text-muted">{children}</kbd>;
}

export function Modal({ open, onOpenChange, title, description, children, footer, size = `md` }) {
  let s = {
      sm: `max-w-md`,
      md: `max-w-xl`,
      lg: `max-w-3xl`,
      xl: `max-w-5xl`,
    }[size],
    c = React.useRef(null);
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-black/55 backdrop-blur-[1px]" />
        <Dialog.Content
          {...(description
            ? {}
            : {
                "aria-describedby": undefined,
              })}
          onOpenAutoFocus={() => {
            c.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
          }}
          onCloseAutoFocus={(e) => {
            (c.current?.isConnected && (e.preventDefault(), c.current.focus()), (c.current = null));
          }}
          className={cn(
            `fixed left-1/2 top-1/2 z-50 flex max-h-[90vh] w-[calc(100vw-2rem)] -translate-x-1/2 -translate-y-1/2 flex-col rounded-lg border border-line bg-panel shadow-2xl`,
            s,
          )}
        >
          <div className="flex items-start justify-between gap-4 border-b border-line px-5 py-3.5">
            <div>
              <Dialog.Title className="text-[15px] font-semibold">{title}</Dialog.Title>
              {description && (
                <Dialog.Description className="mt-0.5 text-xs text-muted">{description}</Dialog.Description>
              )}
            </div>
            <Dialog.Close asChild>
              <IconButton label={msg("Close")}>
                <Icon.X className="size-4" />
              </IconButton>
            </Dialog.Close>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">{children}</div>
          {footer && <div className="flex justify-end gap-2 border-t border-line px-5 py-3">{footer}</div>}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

export var Popover = PopoverPrimitive.Root,
  PopoverTrigger = PopoverPrimitive.Trigger;

export function PopoverContent({ children, className, ...n }) {
  return (
    <PopoverPrimitive.Portal>
      <PopoverPrimitive.Content
        sideOffset={6}
        className={cn(`z-50 rounded-lg border border-line bg-raised p-3 shadow-xl`, className)}
        {...n}
      >
        {children}
      </PopoverPrimitive.Content>
    </PopoverPrimitive.Portal>
  );
}

export function Tabs({ value, onValueChange, tabs, className, listClassName, children }) {
  return (
    <TabsPrimitive.Root value={value} onValueChange={onValueChange} className={cn(`flex min-h-0 flex-col`, className)}>
      <TabsPrimitive.List
        className={cn(`flex shrink-0 gap-0.5 overflow-x-auto border-b border-line px-2`, listClassName)}
      >
        {tabs.map((e) => (
          <TabsPrimitive.Trigger
            value={e.value}
            className="relative flex items-center gap-1 whitespace-nowrap px-2.5 py-2 text-[13px] text-muted hover:text-fg data-[state=active]:text-fg data-[state=active]:after:absolute data-[state=active]:after:inset-x-2 data-[state=active]:after:-bottom-px data-[state=active]:after:h-0.5 data-[state=active]:after:bg-accent"
            key={e.value}
          >
            {e.label}
            {e.badge}
          </TabsPrimitive.Trigger>
        ))}
      </TabsPrimitive.List>
      {children}
    </TabsPrimitive.Root>
  );
}

export var TabPanel = ({ value, children, className }) => (
    <TabsPrimitive.Content value={value} className={cn(`min-h-0 flex-1 overflow-y-auto outline-none`, className)}>
      {children}
    </TabsPrimitive.Content>
  ),
  UiContext = React.createContext(null);

export function UiProvider({ children }) {
  let [t, n] = React.useState([]),
    [r, i] = React.useState(null),
    a = React.useRef(() => {}),
    o = React.useRef(0),
    s = React.useCallback((e, t = `ok`) => {
      let r = ++o.current;
      (n((n) => [
        ...n,
        {
          id: r,
          tone: t,
          text: e,
        },
      ]),
        setTimeout(() => n((e) => e.filter((e) => e.id !== r)), t === `danger` ? 7e3 : 3500));
    }, []),
    c = React.useCallback((e) => (i(e), new Promise((e) => (a.current = e))), []),
    l = (e) => {
      (i(null), a.current(e));
    };
  return (
    <UiContext.Provider
      value={{
        toast: s,
        confirm: c,
      }}
    >
      {children}
      <div
        className="pointer-events-none fixed bottom-4 right-4 z-[60] flex flex-col gap-2"
        role="status"
        aria-live="polite"
      >
        {t.map((e) => (
          <div
            className={cn(
              `pointer-events-auto max-w-sm rounded-md border border-line bg-raised px-3 py-2 text-sm shadow-lg`,
              e.tone === `danger` && `border-danger/40 text-danger`,
              e.tone === `warn` && `text-warn`,
            )}
            key={e.id}
          >
            {e.text}
          </div>
        ))}
      </div>
      <Modal
        open={!!r}
        onOpenChange={(e) => !e && l(false)}
        title={r?.title}
        size="sm"
        footer={
          <>
            <Button variant="ghost" onClick={() => l(false)}>
              {msg("Cancel")}
            </Button>
            <Button variant={r?.danger ? `danger` : `primary`} onClick={() => l(true)} autoFocus>
              {r?.confirmLabel ?? msg("Confirm")}
            </Button>
          </>
        }
      >
        <div className="text-sm text-muted">{r?.body}</div>
      </Modal>
    </UiContext.Provider>
  );
}

export function useUi() {
  let e = React.useContext(UiContext);
  if (!e) throw Error(`UiProvider missing`);
  return e;
}

function initials(e) {
  return e
    .split(/\s+/)
    .map((e) => e[0])
    .join(``)
    .slice(0, 2)
    .toUpperCase();
}

export function Portrait({ assetId, name, variant = `thumb`, className, rounded = `rounded-md` }) {
  let [a, o] = React.useState(null),
    [s, c] = React.useState(null),
    l = !!s && s.id === assetId;
  return (
    React.useEffect(() => {
      if (!s || s.ready) return;
      let e = setTimeout(
        () =>
          c({
            ...s,
            ready: true,
          }),
        1200,
      );
      return () => clearTimeout(e);
    }, [s]),
    !assetId || a === assetId || (l && !s?.ready) ? (
      <div
        className={cn(
          `flex items-center justify-center bg-panel-2 text-faint font-medium select-none border border-line`,
          rounded,
          className,
        )}
        aria-label={msg("{{v0}} (no portrait)", {
          v0: name,
        })}
      >
        <span className="text-[0.8em]">{initials(name || `?`)}</span>
      </div>
    ) : (
      <img
        src={`/api/assets/${assetId}/image?variant=${variant}${l ? `&retry=1` : ``}`}
        alt={name}
        loading="lazy"
        onError={() =>
          l
            ? o(assetId)
            : c({
                id: assetId,
                ready: false,
              })
        }
        className={cn(`object-cover bg-panel-2`, rounded, className)}
        key={l ? `retry` : `first`}
      />
    )
  );
}

export function UploadedImage({ path, name, className }) {
  let [r, i] = React.useState(false);
  return !path || r ? (
    <div
      className={cn(`flex items-center justify-center rounded-md border border-line bg-panel-2 text-faint`, className)}
    >
      <span className="text-[0.8em] font-medium">{initials(name || `?`)}</span>
    </div>
  ) : (
    <img
      src={`/api/uploads/${path}`}
      alt={name}
      onError={() => i(true)}
      className={cn(`rounded-md object-cover`, className)}
    />
  );
}
