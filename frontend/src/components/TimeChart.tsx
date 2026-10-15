// One time-series panel on a shared time axis. Several panels with the same xDomain and syncId
// line up vertically and share a crosshair, so markers (signal start, announcements) align.
import {
  Area,
  Bar,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { C, fmtDate, fmtNum } from "./chartTheme";

export interface SeriesSpec {
  key: string;
  label: string;
  color: string;
  width?: number;
  kind?: "line" | "bar";
}

export interface HLine {
  y: number;
  label: string;
  color: string;
}

export interface Marker {
  t: number;
  label: string;
  strong?: boolean;
}

type Row = Record<string, number | null | [number, number] | undefined> & { t: number };

interface Props {
  title?: string;
  subtitle?: string;
  data: Row[];
  series: SeriesSpec[];
  band?: { key: string; label: string };
  markers?: Marker[];
  hlines?: HLine[];
  xDomain: [number, number];
  height?: number;
  syncId?: string;
  yFormat?: (v: number) => string;
  showXAxis?: boolean;
  legend?: boolean;
}

function TooltipBody({ active, payload, label, series, band, yFormat }: any) {
  if (!active || !payload?.length) return null;
  const row = payload[0].payload as Row;
  return (
    <div className="tt">
      <div className="tt-date">{fmtDate(label)}</div>
      {series.map((s: SeriesSpec) => (
        <div className="tt-row" key={s.key}>
          <span className="tt-key" style={{ background: s.color }} />
          <strong>{row[s.key] === null || row[s.key] === undefined ? "—" : yFormat(row[s.key] as number)}</strong>
          <span className="tt-label">{s.label}</span>
        </div>
      ))}
      {band && Array.isArray(row[band.key]) && (
        <div className="tt-row">
          <span className="tt-key band" />
          <strong>
            {yFormat((row[band.key] as [number, number])[0])}–{yFormat((row[band.key] as [number, number])[1])}
          </strong>
          <span className="tt-label">{band.label}</span>
        </div>
      )}
    </div>
  );
}

export function TimeChart({
  title,
  subtitle,
  data,
  series,
  band,
  markers = [],
  hlines = [],
  xDomain,
  height = 180,
  syncId,
  yFormat = (v) => fmtNum(v),
  showXAxis = true,
  legend = true,
}: Props) {
  return (
    <figure className="panel">
      {(title || legend) && (
        <figcaption>
          {title && <span className="panel-title">{title}</span>}
          {subtitle && <span className="panel-sub">{subtitle}</span>}
          {legend && (
            <span className="legend">
              {series.map((s) => (
                <span key={s.key} className="legend-item">
                  <span className={s.kind === "bar" ? "lg-rect" : "lg-line"} style={{ background: s.color }} />
                  {s.label}
                </span>
              ))}
              {band && (
                <span className="legend-item">
                  <span className="lg-rect band" />
                  {band.label}
                </span>
              )}
            </span>
          )}
        </figcaption>
      )}
      {data.length === 0 ? (
        <div className="empty" style={{ height }}>
          No data in this window
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={height}>
          <ComposedChart data={data} syncId={syncId} syncMethod="value" margin={{ top: 14, right: 16, bottom: 0, left: 0 }}>
            <CartesianGrid stroke={C.grid} vertical={false} />
            <XAxis
              dataKey="t"
              type="number"
              scale="time"
              domain={xDomain}
              allowDataOverflow
              tickFormatter={fmtDate}
              tick={{ fill: C.axis, fontSize: 11 }}
              stroke={C.grid}
              hide={!showXAxis}
              minTickGap={40}
            />
            <YAxis
              width={56}
              tick={{ fill: C.axis, fontSize: 11 }}
              stroke={C.grid}
              tickFormatter={yFormat}
              domain={["auto", "auto"]}
            />
            <Tooltip
              content={<TooltipBody series={series} band={band} yFormat={yFormat} />}
              cursor={{ stroke: C.axis, strokeWidth: 1 }}
              isAnimationActive={false}
            />
            {band && (
              <Area
                dataKey={band.key}
                stroke="none"
                fill={C.band}
                fillOpacity={0.16}
                isAnimationActive={false}
                activeDot={false}
                connectNulls
              />
            )}
            {series.map((s) =>
              s.kind === "bar" ? (
                <Bar key={s.key} dataKey={s.key} fill={s.color} barSize={3} radius={[2, 2, 0, 0]} isAnimationActive={false} />
              ) : (
                <Line
                  key={s.key}
                  dataKey={s.key}
                  stroke={s.color}
                  strokeWidth={s.width ?? 2}
                  dot={false}
                  activeDot={{ r: 4, strokeWidth: 2, stroke: "#fff" }}
                  isAnimationActive={false}
                  connectNulls={false}
                />
              ),
            )}
            {hlines.map((h) => (
              <ReferenceLine
                key={`h-${h.y}`}
                y={h.y}
                stroke={h.color}
                strokeWidth={1}
                ifOverflow="extendDomain"
                label={{ value: h.label, position: "insideBottomLeft", fill: h.color, fontSize: 11 }}
              />
            ))}
            {markers.map((m) => (
              <ReferenceLine
                key={`${m.t}-${m.label}`}
                x={m.t}
                stroke={m.strong ? C.marker : C.announcement}
                strokeWidth={m.strong ? 1.5 : 1}
                ifOverflow="hidden"
                // Signal start labels the top row; announcements sit on a second row so they never collide.
                label={{ value: m.label, position: m.strong ? "insideTopRight" : "insideTopLeft", fill: m.strong ? C.marker : C.text, fontSize: 11,
                         dy: m.strong ? 0 : 13 }}
              />
            ))}
          </ComposedChart>
        </ResponsiveContainer>
      )}
    </figure>
  );
}
