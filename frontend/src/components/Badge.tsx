// Presentational only: colour by status value, grey + hover reason for unknown.
const LABELS: Record<string, string> = {
  entry_review: "Entry signal",
  early_recognition: "Early mover",
  exit_review: "Exit signal",
  watch: "Watching",
  data_gap: "Data gap",
  none: "—",
  early_move: "moving",
  clear_acceleration: "breaking out",
};

export function Badge({ value, reason, kind = "status" }: { value: string; reason?: string | null; kind?: "status" | "stage" }) {
  const cls = `badge ${kind}-${value}`;
  const title = value === "unknown" ? reason ?? "unknown" : reason ?? undefined;
  return (
    <span className={cls} title={title}>
      {LABELS[value] ?? value}
    </span>
  );
}

export function Tag({ children, title }: { children: React.ReactNode; title?: string }) {
  return (
    <span className="tag" title={title}>
      {children}
    </span>
  );
}
