// Chart colours (validated: scripts/validate_palette.js "#2a78d6,#eb6834" --mode light → all checks pass).
// Slot 1 = the product/stock's own series, slot 2 = its comparison series (benchmark, unique accounts).
export const C = {
  series1: "#2a78d6",
  series2: "#eb6834",
  band: "#2a78d6",
  context: "#a3a29d", // daily raw values: context, not a categorical series
  grid: "#ecebe8",
  axis: "#8a8984",
  text: "#52514e",
  marker: "#1d1f23",
  announcement: "#8a8984",
};

export const DAY = 86_400_000;
export const toT = (iso: string) => Date.parse(`${iso}T00:00:00Z`);
export const fmtDate = (t: number) =>
  new Date(t).toLocaleDateString(undefined, { month: "short", day: "numeric", timeZone: "UTC" });
export const fmtNum = (v: number | null | undefined, digits = 1) =>
  v === null || v === undefined ? "—" : v.toLocaleString(undefined, { maximumFractionDigits: digits });
export const fmtCompact = (v: number) =>
  Math.abs(v) >= 1e6 ? `${(v / 1e6).toFixed(1)}M` : Math.abs(v) >= 1e4 ? `${Math.round(v / 1e3)}K` : fmtNum(v);
