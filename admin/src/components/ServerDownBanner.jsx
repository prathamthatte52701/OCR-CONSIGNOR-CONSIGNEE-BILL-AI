import { useEffect, useState } from "react";
import { onServerDownChange, isServerDown } from "../api/client";

export default function ServerDownBanner() {
  const [down, setDown] = useState(isServerDown());

  useEffect(() => {
    const unsubscribe = onServerDownChange(setDown);
    const interval = setInterval(async () => {
      if (!isServerDown()) return;
      try {
        const res = await fetch("/health");
        if (res.ok) setDown(false);
      } catch {
        // still down
      }
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
          Cannot reach THE MAIN OCR backend. This will recover automatically once it responds again.
        </p>
      </div>
    </div>
  );
}
