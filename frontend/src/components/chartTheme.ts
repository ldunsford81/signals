// Dark chart colours (validated: scripts/validate_palette.js "#3987e5,#d95926" --mode dark --surface "#111722" → all pass).
// series1 = product buzz / the stock's own series, series2 = price / the comparison series.
export const C = {
  series1: "#3987e5",
  series2: "#d95926",
  band: "#94a3b8",
  context: "#4a566b", // daily raw values: context, not a categorical series
  grid: "#1a2230",
  axis: "#7f8ba3",
  text: "#9aa6ba",
  marker: "#e6ebf3",
  announcement: "#5b6b85",
};

export const DAY = 86_400_000;
export const toT = (iso: string) => Date.parse(`${iso}T00:00:00Z`);
export const fmtDate = (t: number) =>
  new Date(t).toLocaleDateString(undefined, { month: "short", day: "numeric", timeZone: "UTC" });
export const fmtNum = (v: number | null | undefined, digits = 1) =>
  v === null || v === undefined ? "—" : v.toLocaleString(undefined, { maximumFractionDigits: digits });
export const fmtCompact = (v: number) =>
  Math.abs(v) >= 1e6 ? `${(v / 1e6).toFixed(1)}M` : Math.abs(v) >= 1e4 ? `${Math.round(v / 1e3)}K` : fmtNum(v);
export const pct = (x: number | null | undefined, digits = 1) =>
  x === null || x === undefined ? "n/a" : `${x >= 0 ? "+" : ""}${(x * 100).toFixed(digits)}%`;
