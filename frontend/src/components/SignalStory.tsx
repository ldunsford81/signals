// The signed-out landing illustration: one stylised run showing where each signal fires. Not real data.
import { SignalPill } from "./Signal";

type Pt = [number, number];

/** Smooth path through points (Catmull-Rom converted to cubic Béziers). */
function smooth(pts: Pt[]): string {
  let d = `M${pts[0][0]},${pts[0][1]}`;
  for (let i = 0; i < pts.length - 1; i++) {
    const p0 = pts[i - 1] ?? pts[i];
    const [p1, p2] = [pts[i], pts[i + 1]];
    const p3 = pts[i + 2] ?? p2;
    const c1: Pt = [p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6];
    const c2: Pt = [p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6];
    d += ` C${c1[0].toFixed(1)},${c1[1].toFixed(1)} ${c2[0].toFixed(1)},${c2[1].toFixed(1)} ${p2[0]},${p2[1]}`;
  }
  return d;
}

const W = 560, BASE = 186;
const BUZZ: Pt[] = [[0, 160], [70, 158], [130, 154], [170, 138], [205, 98], [245, 64], [295, 56], [355, 59], [415, 66], [475, 82], [560, 102]];
const PRICE: Pt[] = [[0, 166], [110, 167], [210, 165], [265, 160], [305, 147], [345, 127], [395, 104], [445, 90], [505, 84], [560, 82]];
const CHATTER: Pt[] = [[0, 174], [210, 174], [320, 172], [372, 164], [420, 143], [462, 121], [505, 110], [560, 106]];
const MARKS = [
  { x: 205, n: 1, color: "#199e70" },
  { x: 318, n: 2, color: "#9085e9" },
  { x: 452, n: 3, color: "#e66767" },
];

export const STORY = [
  { n: 1, stage: "entry_review", label: "Entry signal", text: "Buzz is up, the stock hasn't moved yet and retail chatter is quiet." },
  { n: 2, stage: "early_recognition", label: "Early mover", text: "Buzz is up and the price has started to follow." },
  { n: 3, stage: "exit_review", label: "Exit signal", text: "The price has moved and retail chatter has caught up." },
];

export function StoryChart() {
  const buzz = smooth(BUZZ);
  return (
    <figure className="story-chart">
      <svg
        viewBox={`0 0 ${W} 200`}
        role="img"
        aria-label="Illustration: product buzz rises first, the stock price follows, and retail chatter rises last. Markers 1 to 3 show where the entry, early mover and exit signals appear."
      >
        <defs>
          <linearGradient id="buzz-fill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#3987e5" stopOpacity="0.32" />
            <stop offset="1" stopColor="#3987e5" stopOpacity="0" />
          </linearGradient>
        </defs>
        {[60, 100, 140].map((y) => (
          <line key={y} x1="0" x2={W} y1={y} y2={y} stroke="#1a2230" strokeWidth="1" />
        ))}
        <line x1="0" x2={W} y1={BASE} y2={BASE} stroke="#232d3e" strokeWidth="1" />
        {MARKS.map((m) => (
          <line key={m.n} x1={m.x} x2={m.x} y1="26" y2={BASE} stroke={m.color} strokeOpacity="0.45" strokeWidth="1.5" strokeDasharray="3 4" />
        ))}
        <path d={`${buzz} L${W},${BASE} L0,${BASE} Z`} fill="url(#buzz-fill)" className="story-fade" />
        <path d={smooth(CHATTER)} fill="none" stroke="#7f8ba3" strokeWidth="2" strokeDasharray="2 5" strokeLinecap="round" className="story-fade" />
        <path d={smooth(PRICE)} fill="none" stroke="#d95926" strokeWidth="2.5" strokeLinecap="round" pathLength={1} className="story-draw" />
        <path d={buzz} fill="none" stroke="#3987e5" strokeWidth="3" strokeLinecap="round" pathLength={1} className="story-draw" />
        {MARKS.map((m) => (
          <g key={m.n}>
            <circle cx={m.x} cy="16" r="11" fill="#0c1119" stroke={m.color} strokeWidth="2" />
            <text x={m.x} y="20.5" textAnchor="middle" fontSize="12" fontWeight="800" fill="#e6ebf3">
              {m.n}
            </text>
          </g>
        ))}
      </svg>
      <figcaption>
        <span className="legend-item"><span className="lg-line" style={{ background: "#3987e5" }} />Product buzz</span>
        <span className="legend-item"><span className="lg-line" style={{ background: "#d95926" }} />Stock vs. its benchmark</span>
        <span className="legend-item"><span className="lg-line dotted" />Retail chatter</span>
        <span className="story-note">Illustration</span>
      </figcaption>
    </figure>
  );
}

export function StoryList() {
  return (
    <ol className="story-list">
      {STORY.map((s) => (
        <li key={s.n}>
          <span className={`story-num n${s.n}`}>{s.n}</span>
          <div>
            <SignalPill stage={s.stage} label={s.label} size="sm" />
            <p>{s.text}</p>
          </div>
        </li>
      ))}
    </ol>
  );
}
