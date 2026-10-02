import { Component } from "react";
import { AlertTriangle } from "lucide-react";

/**
 * Catches render errors so one broken panel shows a message and a reload
 * button instead of blanking the whole HUD.
 */
export class ErrorBoundary extends Component {
  state = { error: null };

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    console.error(`${this.props.label ?? "HUD"} crashed:`, error, info?.componentStack);
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div
        role="alert"
        className="flex flex-col items-start gap-3 rounded-2xl border border-red-500/40 bg-red-500/10 p-5 text-sm text-red-200"
      >
        <span className="flex items-center gap-2 font-medium">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          {this.props.label ?? "The HUD"} hit an error.
        </span>
        <span className="font-mono text-xs text-red-300/80">
          {this.state.error?.message ?? String(this.state.error)}
        </span>
        <button
          type="button"
          onClick={() => window.location.reload()}
          className="rounded-lg border border-red-400/50 px-3 py-1.5 text-xs font-semibold uppercase tracking-wider hover:bg-red-500/20"
        >
          Reload
        </button>
      </div>
    );
  }
}
