import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Fragment, useState } from "react";
import { Link } from "react-router-dom";
import { evalApi, type AlertLogRow, type AlertQuery, type PerformanceGroup } from "../api/client";
import { Badge, Tag } from "../components/Badge";

const STAGES = ["entry_review", "early_recognition", "exit_review"];
const HORIZON_LABEL: Record<string, string> = { through_earnings: "Through earnings" };
const hLabel = (h: string) => HORIZON_LABEL[h] ?? h.replace("d", " days");
const pct = (x?: number | null, digits = 1) =>
  x === null || x === undefined ? "—" : `${x >= 0 ? "+" : ""}${(x * 100).toFixed(digits)}%`;
const rate = (x?: number | null) => (x === null || x === undefined ? "—" : `${Math.round(x * 100)}%`);
const short = (h: string) => h.slice(0, 8);

function PerformanceTable() {
  const [combine, setCombine] = useState(false);
  const qc = useQueryClient();
  const { data, isFetching } = useQuery({
    queryKey: ["performance", combine],
    queryFn: () => evalApi.performance(combine),
    placeholderData: keepPreviousData,
  });
  const evaluate = useMutation({ mutationFn: evalApi.evaluate, onSettled: () => qc.invalidateQueries() });
  if (!data) return <p>Loading…</p>;
  const hs = data.horizons;

  return (
    <section>
      <div className="filters">
        <h2 className="inline">Rules performance</h2>
        <label className="filter check">
          <input type="checkbox" checked={combine} onChange={(e) => setCombine(e.target.checked)} />
          Combine replay and live alerts
        </label>
        <button className="seg" onClick={() => evaluate.mutate()} disabled={evaluate.isPending}>
          {evaluate.isPending ? "Evaluating…" : "Re-run evaluate"}
        </button>
        <span className="muted small">
          Excess return = stock − benchmark, close to close after the alert date. First alert per company per stage within{" "}
          {data.dedupe_days} days counts once. Fewer than {data.min_sample_to_judge} completed alerts: too few to judge.
        </span>
      </div>
      {data.groups.length === 0 ? (
        <p className="muted">
          No alerts yet. Run <code>ctm replay</code> then <code>ctm evaluate</code> to score the rules on the seeded history.
        </p>
      ) : (
        <div className="table-wrap">
        <table className="grid perf" style={{ opacity: isFetching ? 0.6 : 1 }}>
          <thead>
            <tr>
              <th rowSpan={2}>Stage</th>
              <th rowSpan={2}>Trigger</th>
              <th rowSpan={2}>Config</th>
              <th rowSpan={2} className="num">Alerts<br />(counted)</th>
              <th rowSpan={2}>Hit means</th>
              {hs.map((h) => (
                <th key={h} colSpan={4} className="hgroup">
                  {hLabel(h)}
                </th>
              ))}
            </tr>
            <tr>
              {hs.map((h) => (
                <Fragment key={h}>
                  <th className="num hgroup-start">n</th>
                  <th className="num">Hit rate</th>
                  <th className="num">Median</th>
                  <th className="num">Mean</th>
                </Fragment>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.groups.map((g) => (
              <PerfRow key={`${g.stage}-${g.trigger}-${g.config_hash}`} g={g} hs={hs} current={data.current_config_hash} />
            ))}
          </tbody>
        </table>
        </div>
      )}
    </section>
  );
}

function PerfRow({ g, hs, current }: { g: PerformanceGroup; hs: string[]; current: string }) {
  const hitText = g.hit_rule.startsWith("negative") ? "stock lags benchmark" : "stock beats benchmark";
  return (
    <tr>
      <td>
        <Badge kind="stage" value={g.stage} />
      </td>
      <td>{g.trigger === "all" ? "replay + live" : g.trigger}</td>
      <td className="mono">
        {short(g.config_hash)}
        {g.config_hash === current && <Tag title="The config currently in settings.yaml">current</Tag>}
      </td>
      <td className="num">
        {g.n_alerts} ({g.n_counted})
      </td>
      <td className="small">
        {hitText}
        {g.headline_horizon && <span className="muted"> · judged at {hLabel(g.headline_horizon)}</span>}
      </td>
      {hs.map((h) => {
        const s = g.horizons[h];
        const cls = `${s && !s.judged ? "too-few" : ""} ${g.headline_horizon === h ? "headline" : ""}`;
        if (!s || s.n === 0)
          return (
            <Fragment key={h}>
              <td className={`num hgroup-start ${cls}`}>0</td>
              <td colSpan={3} className={`muted small ${cls}`}>
                no completed outcomes
              </td>
            </Fragment>
          );
        return (
          <Fragment key={h}>
            <td className={`num hgroup-start ${cls}`} title={s.judged ? undefined : "too few to judge"}>
              {s.n}
            </td>
            <td className={`num ${cls}`}>
              <strong>{rate(s.hit_rate)}</strong>
              {!s.judged && <div className="tf-label">too few to judge</div>}
            </td>
            <td className={`num ${cls}`}>{pct(s.median_excess)}</td>
            <td className={`num ${cls}`}>{pct(s.mean_excess)}</td>
          </Fragment>
        );
      })}
    </tr>
  );
}

function SnapshotRow({ id, cols }: { id: number; cols: number }) {
  const { data, isLoading } = useQuery({ queryKey: ["alert", id], queryFn: () => evalApi.alert(id) });
  return (
    <tr className="snapshot-row">
      <td colSpan={cols}>
        {isLoading || !data ? (
          "Loading…"
        ) : (
          <div className="snapshot">
            <p>
              <strong>{data.summary}</strong>
            </p>
            <p className="muted small">
              Alert #{data.id} · scan #{data.scan_id} · {data.trigger} · config {data.config_hash} · created{" "}
              {new Date(`${data.created_at}Z`).toLocaleString()} · prior stage {data.prior_stage ?? "none"}
            </p>
            <details open>
              <summary>Full input snapshot (immutable)</summary>
              <pre>{JSON.stringify(data.input_snapshot, null, 2)}</pre>
            </details>
          </div>
        )}
      </td>
    </tr>
  );
}

function AlertRowView({ a, hs, open, toggle }: { a: AlertLogRow; hs: string[]; open: boolean; toggle: () => void }) {
  return (
    <tr className={open ? "open" : ""}>
      <td>{a.as_of}</td>
      <td className="mono">{a.ticker}</td>
      <td>
        <Link to={`/products/${a.product_id}`}>{a.product}</Link>
      </td>
      <td>
        <Badge kind="stage" value={a.stage} />
      </td>
      <td className="small changes-cell">
        {a.changed_fields
          .map((c: any) => `${c.field === "price_response" ? "Price" : c.field === "retail_status" ? "Retail" : "Stage"}: ${c.from ?? "new"} → ${c.to}`)
          .join(" · ")}
      </td>
      <td>
        {a.trigger}
        {a.rescaled_history && <Tag title="Search data came from a later, rescaled snapshot">rescaled</Tag>}
      </td>
      <td className="mono">{short(a.config_hash)}</td>
      <td>{a.counted ? "yes" : <span className="muted" title="Another alert for this company and stage within the dedupe window already counts">dup</span>}</td>
      <td>{a.decision === "unreviewed" ? <span className="muted">—</span> : a.decision}</td>
      {hs.map((h) => {
        const o = a.outcomes[h];
        return (
          <td key={h} className={`num ${o && !o.complete ? "muted" : ""}`} title={o && !o.complete ? "horizon not finished: return so far" : undefined}>
            {o ? pct(o.excess_return) : "—"}
            {o && !o.complete && o.excess_return !== null && "*"}
          </td>
        );
      })}
      <td>
        <button className="link" onClick={toggle}>
          {open ? "Hide" : "Snapshot"}
        </button>
      </td>
    </tr>
  );
}

function AlertLog() {
  const [q, setQ] = useState<AlertQuery>({ limit: 100 });
  const [open, setOpen] = useState<number | null>(null);
  const { data, isFetching } = useQuery({
    queryKey: ["alerts", q],
    queryFn: () => evalApi.alerts(q),
    placeholderData: keepPreviousData,
  });
  const set = (k: keyof AlertQuery) => (v: string) => setQ({ ...q, [k]: v || undefined, limit: 100 });
  const hs = data?.horizons ?? [];
  const cols = 10 + hs.length;

  return (
    <section>
      <h2>Alert log</h2>
      <div className="filters">
        <label className="filter">
          Stage
          <select value={q.stage ?? ""} onChange={(e) => set("stage")(e.target.value)}>
            <option value="">any</option>
            {STAGES.map((s) => (
              <option key={s}>{s}</option>
            ))}
          </select>
        </label>
        <label className="filter">
          Trigger
          <select value={q.trigger ?? ""} onChange={(e) => set("trigger")(e.target.value)}>
            <option value="">any</option>
            <option value="live">live (daily / manual)</option>
            <option value="replay">replay</option>
          </select>
        </label>
        <label className="filter">
          Config
          <select value={q.config_hash ?? ""} onChange={(e) => set("config_hash")(e.target.value)}>
            <option value="">any</option>
            {(data?.config_hashes ?? []).map((h) => (
              <option key={h} value={h}>
                {short(h)}
              </option>
            ))}
          </select>
        </label>
        <label className="filter">
          From <input type="date" value={q.start ?? ""} onChange={(e) => set("start")(e.target.value)} />
        </label>
        <label className="filter">
          To <input type="date" value={q.end ?? ""} onChange={(e) => set("end")(e.target.value)} />
        </label>
        <span className="count">{data ? `${Math.min(data.items.length, data.total)} of ${data.total} alerts` : ""}</span>
      </div>
      {data && (
        <div className="table-wrap">
        <table className="grid compact alert-log" style={{ opacity: isFetching ? 0.6 : 1 }}>
          <thead>
            <tr>
              <th>As of</th>
              <th>Ticker</th>
              <th>Product</th>
              <th>Stage</th>
              <th>Changes</th>
              <th>Trigger</th>
              <th>Config</th>
              <th>Counted</th>
              <th>Decision</th>
              {hs.map((h) => (
                <th key={h} className="num">
                  Excess {hLabel(h)}
                </th>
              ))}
              <th />
            </tr>
          </thead>
          <tbody>
            {data.items.map((a) => (
              <Fragment key={a.id}>
                <AlertRowView a={a} hs={hs} open={open === a.id} toggle={() => setOpen(open === a.id ? null : a.id)} />
                {open === a.id && <SnapshotRow id={a.id} cols={cols} />}
              </Fragment>
            ))}
          </tbody>
        </table>
        </div>
      )}
      {data && data.items.length < data.total && (
        <p>
          <button className="seg" onClick={() => setQ({ ...q, limit: q.limit + 100 })}>
            Show more
          </button>
        </p>
      )}
      <p className="muted small">* horizon not finished yet: return so far. Alerts are immutable; corrections arrive as new alerts.</p>
    </section>
  );
}

export function Alerts() {
  return (
    <section className="alerts-page">
      <PerformanceTable />
      <AlertLog />
    </section>
  );
}
