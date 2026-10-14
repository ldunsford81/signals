// Presentational only: colour by status value, grey + hover reason for unknown.
const LABELS: Record<string, string> = {
  entry_review: "Entry review",
  early_recognition: "Early recognition",
  exit_review: "Exit review",
  watch: "Watch",
  data_gap: "Data gap",
  none: "—",
  early_move: "early move",
  clear_acceleration: "clear accel.",
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
