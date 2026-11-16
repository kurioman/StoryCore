import * as React from "react";
import { Bug, RotateCcw, TriangleAlert } from "lucide-react";
import { msg } from "@/i18n";
import { ReportProblemDialog } from "@/features/report/ReportProblem";

type Props = { area: string; resetKey?: unknown; compact?: boolean; children: React.ReactNode };

/** Keeps a render error inside one area of the page: the rest of the app keeps working. */
export class ErrorBoundary extends React.Component<Props, { error: Error | null }> {
  state = { error: null as Error | null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error(`[${this.props.area}] render error:`, error, info.componentStack?.split("\n").slice(0, 6).join("\n"));
  }

  componentDidUpdate(prev: Props) {
    if (this.state.error && prev.resetKey !== this.props.resetKey) this.setState({ error: null });
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div role="alert" className={this.props.compact ? "p-4" : "flex h-full items-center justify-center p-8"}>
        <div className="max-w-md rounded-lg border border-danger/30 bg-danger-soft p-4 text-sm">
          <p className="flex items-center gap-2 font-medium text-fg">
            <TriangleAlert className="size-4 text-danger" /> {msg("{{area}} could not be displayed", { area: msg(this.props.area) })}
          </p>
          <p className="mt-1 text-muted">
            {msg("The rest of the app is unaffected and nothing was lost. Details are in the browser console.")}
          </p>
          <p className="mt-1 break-words font-mono text-[11px] text-faint">{this.state.error.message}</p>
          <button
            onClick={() => this.setState({ error: null })}
            className="mt-3 inline-flex items-center gap-1.5 rounded-md border border-line bg-raised px-2.5 py-1 text-xs hover:border-line-strong"
          >
            <RotateCcw className="size-3.5" /> {msg("Try again")}
          </button>
          <ReportButton />
        </div>
      </div>
    );
  }
}

/** Offered on every crashed area: the player can send the problem right away. */
function ReportButton() {
  const [open, setOpen] = React.useState(false);
  const storyId = /^#\/story\/([^/?]+)/.exec(window.location.hash)?.[1];
  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="ml-2 mt-3 inline-flex items-center gap-1.5 rounded-md border border-danger/40 bg-danger-soft px-2.5 py-1 text-xs text-danger hover:border-danger"
      >
        <Bug className="size-3.5" /> {msg("Report a problem")}
      </button>
      <ReportProblemDialog open={open} onClose={() => setOpen(false)} storyId={storyId} />
    </>
  );
}
