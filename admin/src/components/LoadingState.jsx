export default function LoadingState({ message = "Loading..." }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-16 text-text-muted">
      <div className="h-8 w-8 rounded-full border-2 border-border border-t-accent animate-spin" />
      <p className="text-sm">{message}</p>
    </div>
  );
}
