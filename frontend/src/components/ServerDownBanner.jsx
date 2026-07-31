import { useEffect, useState } from "react";
import { onServerDownChange, isServerDown } from "../api/client";

export default function ServerDownBanner() {
  const [down, setDown] = useState(isServerDown());

  useEffect(() => {
    const unsubscribe = onServerDownChange(setDown);
    const ping = async () => {
      try {
        const res = await fetch("/health");
        if (res.ok) setDown(false);
      } catch {
        // still down, banner stays up
      }
    };
    const interval = setInterval(() => {
      if (isServerDown()) ping();
    }, 5000);
    return () => {
      unsubscribe();
      clearInterval(interval);
    };
  }, []);

  if (!down) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-bg/95 backdrop-blur-sm">
      <div className="max-w-sm text-center px-6">
        <div className="mx-auto mb-4 h-10 w-10 rounded-full border-2 border-danger border-t-transparent animate-spin" />
        <h2 className="text-lg font-semibold mb-2">Server unreachable</h2>
        <p className="text-sm text-text-muted">
          We can't reach THE MAIN OCR backend. Check your connection - this page will recover
          automatically once the server responds again.
        </p>
      </div>
    </div>
  );
}
