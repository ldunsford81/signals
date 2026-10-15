// Signal vocabulary shared by every operator view. Colour is never the only cue: each signal has an icon and a label.
import type { ReactNode } from "react";

export const ICONS = {
  up: "M7 17L17 7M9 7h8v8",
  upRight: "M4 16l6-6 4 4 6-6M14 8h6v6",
  down: "M7 7l10 10M17 9v8H9",
  eye: "M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12zM12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z",
  alert: "M12 8v5M12 16h.01M10.3 3.9L2.4 18a2 2 0 0 0 1.7 3h15.8a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z",
  dash: "M5 12h14",
  calendar: "M7 3v3M17 3v3M4 8h16M5 5h14a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1z",
  chat: "M4 5h16v11H8l-4 4z",
  check: "M5 12l4 4 10-10",
  cross: "M7 7l10 10M17 7L7 17",
  chevronRight: "M9 6l6 6-6 6",
  chevronLeft: "M15 6l-6 6 6 6",
  chevronDown: "M6 9l6 6 6-6",
  chevronUp: "M6 15l6-6 6 6",
  search: "M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14zM20 20l-3.5-3.5",
};

export function Icon({ d, size = 14, stroke = 2.4, color = "currentColor" }: { d: string; size?: number; stroke?: number; color?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth={stroke} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={d} />
    </svg>
  );
}

const META: Record<string, { cls: string; icon: string; color: string }> = {
  entry_review: { cls: "pill-entry", icon: ICONS.up, color: "#199e70" },
  early_recognition: { cls: "pill-early", icon: ICONS.upRight, color: "#9085e9" },
  exit_review: { cls: "pill-exit", icon: ICONS.down, color: "#e66767" },
  watch: { cls: "pill-watch", icon: ICONS.eye, color: "#64748b" },
  data_gap: { cls: "pill-gap", icon: ICONS.alert, color: "#64748b" },
  none: { cls: "pill-quiet", icon: ICONS.dash, color: "#3a4559" },
  seasonal: { cls: "pill-seasonal", icon: ICONS.calendar, color: "#64748b" },
  earnings: { cls: "pill-warn", icon: ICONS.calendar, color: "#d7b46a" },
  chatter: { cls: "pill-warn", icon: ICONS.chat, color: "#d7b46a" },
};

export function signalColor(stage: string): string {
  return (META[stage] ?? META.none).color;
}

export function SignalPill({ stage, label, size, kind }: { stage: string; label: string; size?: "sm" | "lg"; kind?: string }) {
  const key = kind ?? (label === "Seasonal" ? "seasonal" : stage);
  const m = META[key] ?? META.none;
  return (
    <span className={`pill ${m.cls} ${size ?? ""}`}>
      <Icon d={m.icon} size={size === "lg" ? 13 : 11} stroke={3} />
      {label}
    </span>
  );
}

/** Product buzz (blue, filled) against the stock relative to its benchmark (orange), indexed to 100 on one axis. */
export function DualSpark({ buzz, price, label, height = 64 }: { buzz: (number | null)[]; price: (number | null)[]; label: string; height?: number }) {
  const W = 300;
  const vals = [...buzz, ...price].filter((v): v is number => v !== null);
  if (vals.length < 2) return <div className="empty" style={{ height }}>No history yet</div>;
  const lo = Math.min(...vals) - 6;
  const hi = Math.max(...vals) + 6;
  const y = (v: number) => 2 + (height - 4) * (1 - (v - lo) / (hi - lo || 1));
  const path = (arr: (number | null)[], n: number, offset = 0) =>
    arr
      .map((v, i) => (v === null ? null : `${((i + offset) / (n - 1)) * W},${y(v).toFixed(1)}`))
      .filter(Boolean)
      .map((p, i) => (i ? "L" : "M") + p)
      .join(" ");
  const n = Math.max(buzz.length, 2);
  const buzzLine = path(buzz, n);
  const priceLine = path(price, price.length || 2);
  return (
    <svg width="100%" height={height} viewBox={`0 0 ${W} ${height}`} preserveAspectRatio="none" role="img" aria-label={label}>
      {buzzLine && <path d={`${buzzLine} L${W},${height} L0,${height} Z`} fill="#3987e5" fillOpacity={0.14} />}
      <path d={buzzLine} fill="none" stroke="#3987e5" strokeWidth={2} vectorEffect="non-scaling-stroke" />
      <path d={priceLine} fill="none" stroke="#d95926" strokeWidth={2} vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

export function MiniSpark({ values, active, label }: { values: (number | null)[]; active: boolean; label: string }) {
  const W = 120;
  const H = 28;
  const vals = values.filter((v): v is number => v !== null);
  if (vals.length < 2) return <svg width={W} height={H} aria-hidden="true" />;
  const lo = Math.min(...vals, 90);
  const hi = Math.max(...vals, 160);
  const d = values
    .map((v, i) => (v === null ? null : `${((i / (values.length - 1)) * W).toFixed(1)},${(2 + (H - 4) * (1 - (v - lo) / (hi - lo))).toFixed(1)}`))
    .filter(Boolean)
    .map((p, i) => (i ? "L" : "M") + p)
    .join(" ");
  return (
    <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} role="img" aria-label={label}>
      <path d={d} fill="none" stroke={active ? "#3987e5" : "#4a566b"} strokeWidth={1.8} strokeLinejoin="round" />
    </svg>
  );
}

export function ChatterDots({ level }: { level: string }) {
  const n = { quiet: 1, rising: 2, elevated: 3 }[level] ?? 0;
  const color = { quiet: "#5b6b85", rising: "#d7b46a", elevated: "#e66767" }[level] ?? "#232d3e";
  return (
    <span className="dots" aria-hidden="true">
      {[1, 2, 3].map((i) => (
        <i key={i} style={{ background: i <= n ? color : undefined }} />
      ))}
    </span>
  );
}

export function SectionHead({ title, note, children }: { title: ReactNode; note?: ReactNode; children?: ReactNode }) {
  return (
    <div className="section-head">
      <h2>{title}</h2>
      {note && <span className="section-note">{note}</span>}
      {children}
    </div>
  );
}

export const STAGE_LABEL: Record<string, string> = {
  entry_review: "Entry signal",
  early_recognition: "Early mover",
  exit_review: "Exit signal",
  watch: "Watching",
  data_gap: "Data gap",
  none: "Quiet",
};
