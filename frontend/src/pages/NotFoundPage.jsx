import { Link } from "react-router-dom";

export default function NotFoundPage() {
  return (
    <div className="min-h-screen flex flex-col items-center justify-center gap-3 text-center px-4">
      <h1 className="text-4xl font-bold text-accent">404</h1>
      <p className="text-text-muted">Page not found.</p>
      <Link to="/dashboard" className="text-sm text-accent hover:underline">
        Back to dashboard
      </Link>
    </div>
  );
}
