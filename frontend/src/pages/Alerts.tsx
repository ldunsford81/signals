import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Fragment, useState } from "react";
import { Link } from "react-router-dom";
import { evalApi, type AlertLogRow, type AlertQuery, type PerformanceGroup } from "../api/client";
import { isAdmin, useUser } from "../components/Auth";
import { Badge, Tag } from "../components/Badge";
import { SignalPill, signalColor, STAGE_LABEL } from "../components/Signal";

const STAGES = ["entry_review", "early_recognition", "exit_review"];
const HORIZON_LABEL: Record<string, string> = { through_earnings: "Through earnings" };
const hLabel = (h: string) => HORIZON_LABEL[h] ?? h.replace("d", " days");
const pct = (x?: number | null, digits = 1) =>
  x === null || x === undefined ? "—" : `${x >= 0 ? "+" : ""}${(x * 100).toFixed(digits)}%`;
const rate = (x?: number | null) => (x === null || x === undefined ? "—" : `${Math.round(x * 100)}%`);
const short = (h: string) => h.slice(0, 8);
const WORDS: Record<string, string> = { ...STAGE_LABEL, early_move: "moving", clear_acceleration: "breaking out" };
const word = (v?: string | null) => (v ? WORDS[v] ?? v : "new");

function PerformanceTable() {
  const [combine, setCombine] = useState(false);
  const [horizon, setHorizon] = useState("20d");
  const qc = useQueryClient();
  const { data, isFetching } = useQuery({
    queryKey: ["performance", combine],
    queryFn: () => evalApi.performance(combine),
    placeholderData: keepPreviousData,
  });
  const evaluate = useMutation({ mutationFn: evalApi.evaluate, onSettled: () => qc.invalidateQueries() });
  const admin = isAdmin(useUser());
  if (!data) return <p>Loading…</p>;
  const hs = data.horizons;

  return (
    <section style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <div className="section-head">
        <h2>
          How each signal performed <span>· excess return vs benchmark after the signal</span>
        </h2>
        <span style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          {hs.map((h) => (
            <button key={h} className={`seg ${h === horizon ? "on" : ""}`} onClick={() => setHorizon(h)}>
              {hLabel(h)}
            </button>
          ))}
        </span>
      </div>
      {data.groups.length === 0 ? (
        <div className="empty-card">
          No signals scored yet. Run <code>socialarb replay</code> then <code>socialarb evaluate</code> (an admin can also use the buttons in Data &amp; settings) to score
          the rules on the seeded history.
        </div>
      ) : (
        <div className="tboard" style={{ opacity: isFetching ? 0.6 : 1 }}>
          <div style={{ minWidth: 820 }}>
            <div className="prow head">
              <span>Signal</span>
              <span>Source</span>
              <span className="r">Signals</span>
              <span>Hit rate · {hLabel(horizon)}</span>
              <span className="r">Median</span>
              <span className="r">Mean</span>
              <span>A hit means</span>
            </div>
            {data.groups.map((g) => (
              <PerfRow key={`${g.stage}-${g.trigger}-${g.config_hash}`} g={g} h={horizon} current={data.current_config_hash} />
            ))}
          </div>
        </div>
      )}
      <div className="filters" style={{ margin: 0 }}>
        <label className="filter check">
          <input type="checkbox" checked={combine} onChange={(e) => setCombine(e.target.checked)} />
          Combine replay and live signals
        </label>
        {admin && (
          <button className="seg" onClick={() => evaluate.mutate()} disabled={evaluate.isPending}>
            {evaluate.isPending ? "Evaluating…" : "Re-run evaluate"}
          </button>
        )}
        <span className="muted small">
          Close to close after the signal date. The first signal per company per stage within {data.dedupe_days} days counts once. Fewer
          than {data.min_sample_to_judge} finished signals: too few to judge.
        </span>
      </div>
    </section>
  );
}

function PerfRow({ g, h, current }: { g: PerformanceGroup; h: string; current: string }) {
  const s = g.horizons[h];
  const negative = g.hit_rule.startsWith("negative");
  const judged = s?.judged ?? false;
  const rateVal = s?.hit_rate ?? null;
  return (
    <div className={`prow ${judged ? "" : "dim"}`}>
      <span>
        <SignalPill stage={g.stage} label={STAGE_LABEL[g.stage] ?? g.stage} size="sm" />
      </span>
      <span className="small">
        {g.trigger === "all" ? "replay + live" : g.trigger === "replay" ? "history replay" : "live"}
        <span className="muted mono" style={{ marginLeft: 8 }}>
          {short(g.config_hash)}
          {g.config_hash === current ? "" : " (old config)"}
        </span>
      </span>
      <span className="r num-mono">
        {s?.n ?? 0}
        <span className="muted"> / {g.n_counted}</span>
      </span>
      <span style={{ display: "flex", alignItems: "center", gap: 10 }}>
        {rateVal === null ? (
          <span className="muted small">not finished yet</span>
        ) : (
          <>
            <span className="meter" style={{ flexBasis: 120 }}>
              <span style={{ width: `${Math.round(rateVal * 100)}%`, background: signalColor(g.stage) }} />
            </span>
            <b className="num-mono">{rate(rateVal)}</b>
            {!judged && <span className="tf-label">too few to judge</span>}
          </>
        )}
      </span>
      <span className="r num-mono">{pct(s?.median_excess)}</span>
      <span className="r num-mono">{pct(s?.mean_excess)}</span>
      <span className="small muted">
        {negative ? "stock lags benchmark" : "stock beats benchmark"}
        {g.headline_horizon && ` · judged at ${hLabel(g.headline_horizon)}`}
      </span>
    </div>
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
        <Link to={`/tickers/${a.ticker}?product=${a.product_id}`}>{a.product}</Link>
      </td>
      <td>
        <Badge kind="stage" value={a.stage} />
      </td>
      <td className="small changes-cell">
        {a.changed_fields
          .map((c: any) => `${c.field === "price_response" ? "Price" : c.field === "retail_status" ? "Chatter" : "Signal"}: ${word(c.from)} → ${word(c.to)}`)
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
  const [q, setQ] = useState<AlertQuery>({ limit: 25 });
  const [open, setOpen] = useState<number | null>(null);
  const { data, isFetching } = useQuery({
    queryKey: ["alerts", q],
    queryFn: () => evalApi.alerts(q),
    placeholderData: keepPreviousData,
  });
  const set = (k: keyof AlertQuery) => (v: string) => setQ({ ...q, [k]: v || undefined, limit: 25 });
  const hs = data?.horizons ?? [];
  const cols = 10 + hs.length;

  return (
    <section>
      <h2>Signal log <span className="muted" style={{ fontWeight: 500, fontSize: 13 }}>· every signal ever written, with how it turned out</span></h2>
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
          <button className="seg" onClick={() => setQ({ ...q, limit: q.limit + 50 })}>
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
      <header className="page-head" style={{ marginBottom: 8 }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <span className="eyebrow">How past signals turned out</span>
          <h1>Performance</h1>
        </div>
      </header>
      <PerformanceTable />
      <AlertLog />
    </section>
  );
}
