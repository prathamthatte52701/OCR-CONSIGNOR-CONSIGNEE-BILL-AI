import { Component, lazy, Suspense } from "react";

// pdfjs-dist is large; load the viewer (and with it PDF.js + its worker) only when a page
// actually shows a file. Pages import this wrapper, never DocumentViewer directly.
const DocumentViewer = lazy(() => import("./DocumentViewer"));

const DEFAULT_HEIGHT = "h-[56vh] min-h-[360px]";
const shell = "min-w-0 overflow-hidden rounded-lg border border-border bg-bg";

class ViewerBoundary extends Component {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(error) {
    console.error("Document viewer failed:", error);
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <div className={`${shell} grid place-items-center gap-3 px-4 text-center ${this.props.heightClass}`}>
        <div>
          <p className="mb-3 text-sm font-medium text-text-muted">Could not load the viewer.</p>
          <button
            type="button"
            onClick={() => window.location.reload()}
            className="rounded border border-border bg-surface-raised px-4 py-2 text-xs font-medium hover:bg-accent/10"
          >
            Reload
          </button>
        </div>
      </div>
    );
  }
}

export default function LazyDocumentViewer({ heightClass = DEFAULT_HEIGHT, ...props }) {
  return (
    <ViewerBoundary heightClass={heightClass}>
      <Suspense
        fallback={
          <div className={`${shell} grid place-items-center text-sm text-text-muted ${heightClass}`}>
            Loading viewer...
          </div>
        }
      >
        <DocumentViewer heightClass={heightClass} {...props} />
      </Suspense>
    </ViewerBoundary>
  );
}
