import { Component } from "react";

// Last-resort safety net: if any page throws while rendering (for example an unexpected API
// response shape), show a recoverable message instead of a blank white screen.
export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    console.error("UI crashed:", error, info?.componentStack);
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="mx-auto max-w-md px-4 py-24 text-center">
        <h1 className="mb-2 text-xl font-semibold">Something went wrong</h1>
        <p className="mb-6 text-sm text-text-muted">
          This page hit an unexpected problem. Your data is safe - reload to try again.
        </p>
        <button
          onClick={() => window.location.reload()}
          className="rounded bg-accent px-5 py-2 text-sm font-medium text-bg hover:bg-accent-dim"
        >
          Reload page
        </button>
      </div>
    );
  }
}
