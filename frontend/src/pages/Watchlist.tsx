import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api, type WatchlistQuery, type WatchlistRow } from "../api/client";
import { Badge, Tag } from "../components/Badge";

const STAGES = ["exit_review", "entry_review", "early_recognition", "watch", "data_gap", "none"];
const ATTENTION = ["elevated", "normal", "seasonal", "unknown"];
const PRICE = ["flat", "early_move", "clear_acceleration", "unknown"];
const RETAIL = ["quiet", "rising", "elevated", "unknown"];

function Select({ label, value, options, onChange }: { label: string; value?: string; options: string[]; onChange: (v?: string) => void }) {
  return (
    <label className="filter">
      {label}
      <select value={value ?? ""} onChange={(e) => onChange(e.target.value || undefined)}>
        <option value="">any</option>
        {options.map((o) => (
          <option key={o} value={o}>
            {o}
          </option>
        ))}
      </select>
    </label>
  );
}

function pct(x?: number | null) {
  return x === null || x === undefined ? "" : `${x >= 0 ? "+" : ""}${(x * 100).toFixed(1)}%`;
}

function Row({ r }: { r: WatchlistRow }) {
  return (
    <tr>
      <td>
        {r.company}
        {r.is_demo && <Tag title="Fictional demo company">demo</Tag>}
      </td>
      <td className="mono">{r.ticker}</td>
      <td>
        <Link to={`/products/${r.product_id}`}>{r.product}</Link>
      </td>
      <td>
        <Badge kind="stage" value={r.stage} />
      </td>
      <td>
        <Badge
          value={r.attention.status}
          reason={r.attention.seasonal ? "Same window last year was similar: year-over-year ratio below threshold" : r.attention.reason}
        />
        {r.attention.single_source && <Tag title="Only one attention source is healthy">single_source</Tag>}
        {r.rescaled_history && <Tag title="Uses a later, rescaled snapshot (replay)">rescaled</Tag>}
      </td>
      <td>
        <Badge value={r.price.status} reason={r.price.reason} />
        {r.price.relative_return !== null && r.price.relative_return !== undefined && (
          <span className="sub" title={`relative to ${r.price.benchmark}; volume ratio ${r.price.volume_ratio ?? "n/a"}`}>
            {pct(r.price.relative_return)}
          </span>
        )}
      </td>
      <td>
        <Badge value={r.retail.status} reason={r.retail.reason} />
      </td>
      <td className="num">
        {r.earnings_status === "unknown" ? (
          <Badge value="unknown" reason={r.earnings_reason} />
        ) : (
          <>
            {r.days_to_earnings}
            {r.earnings_projected && <Tag title={`Projected date ${r.next_earnings_date}, not confirmed`}>projected</Tag>}
          </>
        )}
      </td>
      <td className="num">
        {r.days_left_in_quarter === null || r.days_left_in_quarter === undefined ? (
          "—"
        ) : r.quarter_closed ? (
          <Tag title="Attention from here on mostly lands in the following print">reporting quarter closed</Tag>
        ) : (
          r.days_left_in_quarter
        )}
      </td>
    </tr>
  );
}

export function Watchlist() {
  const [q, setQ] = useState<WatchlistQuery>({ earnings_window: true });
  const { data, isLoading, error } = useQuery({ queryKey: ["watchlist", q], queryFn: () => api.watchlist(q) });
  const set = (k: keyof WatchlistQuery) => (v?: string) => setQ({ ...q, [k]: v });
  const [lo, hi] = data?.earnings_window_days ?? [42, 98];

  return (
    <section>
      <div className="filters">
        <Select label="Stage" value={q.stage} options={STAGES} onChange={set("stage")} />
        <Select label="Attention" value={q.attention} options={ATTENTION} onChange={set("attention")} />
        <Select label="Price" value={q.price} options={PRICE} onChange={set("price")} />
        <Select label="Retail" value={q.retail} options={RETAIL} onChange={set("retail")} />
        <label className="filter check">
          <input type="checkbox" checked={q.earnings_window} onChange={(e) => setQ({ ...q, earnings_window: e.target.checked })} />
          Earnings in {Math.round(lo / 7)}–{Math.round(hi / 7)} weeks
        </label>
        <span className="count">{data ? `${data.rows.length} of ${data.total} products` : ""}</span>
      </div>
      {isLoading && <p>Loading…</p>}
      {error && <p className="error">{String(error)}</p>}
      {data && !data.scan && <p>No scan yet. Seed the demo and run a scan (see README).</p>}
      {data && data.scan && (
        <table className="grid">
          <thead>
            <tr>
              <th>Company</th>
              <th>Ticker</th>
              <th>Product</th>
              <th>Stage</th>
              <th>Product attention</th>
              <th>Price response</th>
              <th>Retail interest</th>
              <th className="num">Days to earnings</th>
              <th className="num">Days left in quarter</th>
            </tr>
          </thead>
          <tbody>
            {data.rows.map((r) => (
              <Row key={r.product_id} r={r} />
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
