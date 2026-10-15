import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { productApi, type ProductDetail, type SourceSeries } from "../api/client";
import { Badge, Tag } from "../components/Badge";
import { C, fmtCompact, fmtNum, toT } from "../components/chartTheme";
import { TimeChart, type Marker } from "../components/TimeChart";

const RANGES = [90, 180, 365];

const SOURCE_LABEL: Record<string, string> = {
  search_interest: "Search interest (0–100 index)",
  social_mentions: "Social mentions",
  ticker_search_interest: "“TICKER stock” search interest (0–100 index)",
  cashtag_mentions: "Cashtag mentions",
};

const FIELD_LABEL: Record<string, string> = { stage: "Stage", price_response: "Price", retail_status: "Retail" };

const pct = (x: unknown) => (typeof x === "number" ? `${x >= 0 ? "+" : ""}${(x * 100).toFixed(1)}%` : "—");
const n = (x: unknown, d = 2) => (typeof x === "number" ? fmtNum(x, d) : "—");

function bandRows(s: SourceSeries) {
  return s.points.map((p) => ({
    t: toT(p.date),
    value: p.value,
    short_mean: p.short_mean,
    breadth_short_mean: p.breadth_short_mean ?? null,
    band: p.band_low !== null && p.band_high !== null ? ([Math.max(0, p.band_low), p.band_high] as [number, number]) : undefined,
  }));
}

function Health({ h }: { h: any }) {
  if (!h) return <>—</>;
  return h.healthy ? <span className="ok">healthy</span> : <Badge value="unknown" reason={h.reason} />;
}

function SourceTitle({ source, ticker }: { source: string; ticker: string }) {
  return <>{(SOURCE_LABEL[source] ?? source).replace("TICKER", ticker)}</>;
}

export function Detail() {
  const { id } = useParams();
  const [days, setDays] = useState(180);
  const { data, error, isLoading, isFetching } = useQuery({
    queryKey: ["product", id, days],
    queryFn: () => productApi.detail(Number(id), days),
    placeholderData: keepPreviousData,
  });

  if (isLoading) return <p>Loading…</p>;
  if (error) return <p className="error">{String(error)}</p>;
  if (!data) return null;
  const d = data as ProductDetail;
  const st = d.state;
  const ticker = d.company.ticker;

  return (
    <section className="detail" style={{ opacity: isFetching ? 0.6 : 1 }}>
      <p className="crumbs">
        <Link to="/">← Watchlist</Link>
      </p>
      <header className="detail-head">
        <div>
          <h1>
            {d.product.name} <span className="muted">· {d.company.name}</span> <span className="mono">{ticker}</span>
            {d.company.is_demo && <Tag>demo</Tag>}
          </h1>
          <p className="muted">
            Keywords: {d.product.keywords.join(", ") || "—"} · {d.company.sector} · benchmark {d.company.benchmark}
            {d.scan && <> · as of {d.scan.as_of}</>}
          </p>
        </div>
        {st && (
          <div className="head-badges">
            <div>
              <span className="lbl">Stage</span>
              <Badge kind="stage" value={st.stage} />
            </div>
            <div>
              <span className="lbl">Product attention</span>
              <Badge value={st.attention_status} reason={st.attention_components.reason as string | undefined} />
            </div>
            <div>
              <span className="lbl">Price response</span>
              <Badge value={st.price_response} reason={st.price_components.reason as string | undefined} />
            </div>
            <div>
              <span className="lbl">Retail interest</span>
              <Badge value={st.retail_status} reason={st.retail_components.reason as string | undefined} />
            </div>
          </div>
        )}
      </header>

      {!st ? (
        <p>This product has not been scanned yet. Run a scan to see its signals.</p>
      ) : (
        <DetailBody d={d} days={days} setDays={setDays} />
      )}
    </section>
  );
}

export function DetailBody({ d, days, setDays }: { d: ProductDetail; days: number; setDays: (n: number) => void }) {
  const st = d.state!;
  const ticker = d.company.ticker;
  const health = st.input_health as any;
  const earn = health.earnings ?? {};
  const ac = st.attention_components as any;
  const pc = st.price_components as any;
  const rc = st.retail_components as any;
  const asOfT = toT(d.scan!.as_of);
  const xDomain: [number, number] = [toT(d.window_start!), asOfT];

  const markers: Marker[] = [];
  if (st.signal_start_date) markers.push({ t: toT(st.signal_start_date), label: "Signal start", strong: true });
  d.announcements.forEach((a, i) => markers.push({ t: toT(a.event_date), label: `A${i + 1}` }));

  const priceRows = d.price_series.map((p) => ({ t: toT(p.date), close: p.close, bench: p.benchmark_rebased, volume: p.volume }));

  return (
    <>
      <div className="facts">
        <div>
          <span className="lbl">Next earnings</span>
          {earn.status === "unknown" ? (
            <Badge value="unknown" reason={earn.reason} />
          ) : (
            <>
              <strong>{earn.next_earnings_date}</strong> ({st.days_to_earnings} days)
              {earn.confirmed === false && <Tag title="Not confirmed by the company">projected</Tag>}
            </>
          )}
        </div>
        <div>
          <span className="lbl">Fiscal quarter end</span>
          <strong>{earn.fiscal_quarter_end ?? "—"}</strong>
          {st.days_left_in_quarter !== null && st.days_left_in_quarter !== undefined && (
            <>
              {" "}
              {st.days_left_in_quarter > 0 ? (
                `(${st.days_left_in_quarter} days left)`
              ) : (
                <Tag title="Attention from here on mostly lands in the following print">reporting quarter closed</Tag>
              )}
            </>
          )}
        </div>
        <div>
          <span className="lbl">Signal start</span>
          <strong>{st.signal_start_date ?? "no active signal"}</strong>
        </div>
        <div>
          <span className="lbl">Flags</span>
          {health.flags?.single_source && <Tag>single_source</Tag>}
          {health.flags?.seasonal && <Tag>seasonal</Tag>}
          {health.flags?.rescaled_history && <Tag>rescaled_history</Tag>}
          {!health.flags?.single_source && !health.flags?.seasonal && !health.flags?.rescaled_history && "—"}
        </div>
      </div>

      <div className="filters">
        <span className="filter">Window</span>
        {RANGES.map((r) => (
          <button key={r} className={`seg ${r === days ? "on" : ""}`} onClick={() => setDays(r)}>
            {r} days
          </button>
        ))}
        {d.announcements.length > 0 && <span className="muted">A1… = announcements, listed below</span>}
      </div>

      {/* ---- product attention ---- */}
      <h2>Product attention</h2>
      <div className="panels">
        {d.attention_series.map((s) => (
          <TimeChart
            key={s.source}
            title={(SOURCE_LABEL[s.source] ?? s.source).replace("TICKER", ticker)}
            subtitle={s.rescaled_history ? "rescaled snapshot" : undefined}
            data={bandRows(s)}
            series={[
              { key: "short_mean", label: `${s.short_window}-day mean`, color: C.series1 },
              { key: "value", label: "daily", color: C.context, width: 1 },
            ]}
            band={{ key: "band", label: "baseline mean ± 2σ" }}
            markers={markers}
            xDomain={xDomain}
            syncId="detail"
          />
        ))}
      </div>
      <table className="grid compact">
        <thead>
          <tr>
            <th>Source</th>
            <th>Health</th>
            <th className="num">Ratio</th>
            <th className="num">z</th>
            <th className="num">Short mean</th>
            <th className="num">Baseline mean</th>
            <th className="num">Baseline std</th>
            <th className="num">Accelerating days (of 5)</th>
            <th>Persistent</th>
          </tr>
        </thead>
        <tbody>
          {Object.values(ac.sources ?? {}).map((c: any) => (
            <tr key={c.source}>
              <td>
                <SourceTitle source={c.source} ticker={ticker} />
              </td>
              <td>
                <Health h={c} />
              </td>
              <td className="num">{n(c.ratio)}</td>
              <td className="num">{n(c.z)}</td>
              <td className="num">{n(c.short_mean, 1)}</td>
              <td className="num">{n(c.baseline_mean, 1)}</td>
              <td className="num">{n(c.baseline_std, 1)}</td>
              <td className="num">{c.accelerating_days ?? "—"}</td>
              <td>{c.persistent === undefined ? "—" : c.persistent ? "yes" : "no"}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="note">
        Needs {ac.needed_sources ?? "—"} accelerating source(s) on 4 of the last 5 days · score {n(st.attention_score)} ·
        seasonality: {ac.seasonality?.result ?? "—"}
        {ac.seasonality?.median_yoy !== undefined && ` (median YoY ${n(ac.seasonality.median_yoy)}, min ${ac.seasonality.min_yoy_ratio})`}
      </p>

      {/* ---- price response ---- */}
      <h2>Price response</h2>
      <div className="panels">
        <TimeChart
          title={`${ticker} close`}
          subtitle={
            d.benchmark_rebased_on
              ? `${d.company.benchmark} rebased to ${ticker} on ${d.benchmark_rebased_on}${pc.base_date ? " (anchor base)" : " (window start)"}`
              : undefined
          }
          data={priceRows}
          series={[
            { key: "close", label: ticker, color: C.series1 },
            { key: "bench", label: `${d.company.benchmark} (rebased)`, color: C.series2 },
          ]}
          markers={markers}
          xDomain={xDomain}
          syncId="detail"
          yFormat={(v) => v.toFixed(v < 10 ? 2 : 0)}
          height={220}
        />
        <TimeChart
          title="Volume"
          subtitle={`5-day / 60-day ratio ${n(pc.volume_ratio)}`}
          data={priceRows}
          series={[{ key: "volume", label: "volume", color: C.series1, kind: "bar" }]}
          markers={markers}
          xDomain={xDomain}
          syncId="detail"
          height={110}
          legend={false}
          yFormat={fmtCompact}
        />
      </div>
      <table className="grid compact kv">
        <tbody>
          <tr>
            <th>Anchor</th>
            <td>{pc.anchor_label === "signal_start" ? `signal start ${pc.anchor_date}` : pc.anchor_label === "no_anchor" ? "no active signal: 20-session lookback (no_anchor)" : "—"}</td>
            <th>Base close date</th>
            <td>{pc.base_date ?? "—"}</td>
          </tr>
          <tr>
            <th>Stock return</th>
            <td>{pct(pc.stock_return)}</td>
            <th>{d.company.benchmark} return</th>
            <td>{pct(pc.benchmark_return)}</td>
          </tr>
          <tr>
            <th>Relative return</th>
            <td>
              <strong>{pct(pc.relative_return)}</strong>
            </td>
            <th>Volume ratio</th>
            <td>{n(pc.volume_ratio)}</td>
          </tr>
          {pc.reason && (
            <tr>
              <th>Unknown because</th>
              <td colSpan={3}>{pc.reason}</td>
            </tr>
          )}
        </tbody>
      </table>

      {/* ---- retail interest ---- */}
      <h2>Retail interest</h2>
      <div className="panels">
        {d.retail_series.map((s) => (
          <TimeChart
            key={s.source}
            title={(SOURCE_LABEL[s.source] ?? s.source).replace("TICKER", ticker)}
            subtitle={[
              s.rescaled_history ? "rescaled snapshot" : "",
              s.breadth_metric && !s.points.some((p) => p.breadth_short_mean != null)
                ? `${s.breadth_metric.replace("_", " ")} not sampled for this name: capped at rising`
                : "",
            ].filter(Boolean).join(" · ") || undefined}
            data={bandRows(s)}
            series={[
              { key: "short_mean", label: `${s.short_window}-day mean`, color: C.series1 },
              ...(s.breadth_metric && s.points.some((p) => p.breadth_short_mean !== null && p.breadth_short_mean !== undefined)
                ? [{ key: "breadth_short_mean", label: `${s.breadth_metric.replace("_", " ")} (${s.short_window}-day mean)`, color: C.series2 }]
                : []),
              { key: "value", label: "daily", color: C.context, width: 1 },
            ]}
            band={{ key: "band", label: "baseline mean ± 2σ" }}
            markers={markers}
            xDomain={xDomain}
            syncId="detail"
          />
        ))}
      </div>
      <table className="grid compact">
        <thead>
          <tr>
            <th>Source</th>
            <th>Health</th>
            <th>Level</th>
            <th className="num">Ratio</th>
            <th className="num">z</th>
            <th className="num">Short mean</th>
            <th className="num">Baseline mean</th>
            <th>Unique-account check</th>
          </tr>
        </thead>
        <tbody>
          {Object.values(rc.sources ?? {}).map((c: any) => (
            <tr key={c.source}>
              <td>
                <SourceTitle source={c.source} ticker={ticker} />
                {rc.set_by === c.source && <Tag title="This source set the family status">sets status</Tag>}
              </td>
              <td>
                <Health h={c} />
              </td>
              <td>{c.level ? <Badge value={c.level} /> : "—"}</td>
              <td className="num">{n(c.ratio)}</td>
              <td className="num">{n(c.z)}</td>
              <td className="num">{n(c.short_mean, 1)}</td>
              <td className="num">{n(c.baseline_mean, 1)}</td>
              <td>
                {c.breadth
                  ? c.breadth.result === "outside_sample"
                    ? "outside post sample: capped at rising"
                    : `${c.breadth.result} (ratio ${n(c.breadth.ratio)}, needs ${c.breadth.min_ratio})`
                  : "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {/* ---- announcements, history, alerts ---- */}
      <h2>Announcements</h2>
      {d.announcements.length === 0 ? (
        <p className="muted">None in this window.</p>
      ) : (
        <table className="grid compact">
          <thead>
            <tr>
              <th>Marker</th>
              <th>Date</th>
              <th>Type</th>
              <th>Title</th>
              <th>Scope</th>
            </tr>
          </thead>
          <tbody>
            {d.announcements.map((a, i) => (
              <tr key={a.id}>
                <td className="mono">A{i + 1}</td>
                <td>{a.event_date}</td>
                <td>{a.type.replace("_", " ")}</td>
                <td>{a.url ? <a href={a.url}>{a.title}</a> : a.title}</td>
                <td>{a.product_id ? "this product" : "company"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <div className="two-col">
        <div>
          <h2>Stage history</h2>
          <table className="grid compact">
            <thead>
              <tr>
                <th>As of</th>
                <th>Stage</th>
                <th>Attention</th>
                <th>Price</th>
                <th>Retail</th>
                <th className="num">Days to earn.</th>
                <th>Trigger</th>
              </tr>
            </thead>
            <tbody>
              {d.history.map((h) => (
                <tr key={h.scan_id}>
                  <td>{h.as_of}</td>
                  <td>
                    <Badge kind="stage" value={h.stage} />
                  </td>
                  <td>{h.attention}</td>
                  <td>{h.price}</td>
                  <td>{h.retail}</td>
                  <td className="num">{h.days_to_earnings ?? "—"}</td>
                  <td className="muted">{h.trigger}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div>
          <h2>Alerts</h2>
          {d.alerts.length === 0 ? (
            <p className="muted">No alerts for this product.</p>
          ) : (
            <table className="grid compact wrap">
              <thead>
                <tr>
                  <th>As of</th>
                  <th>Stage</th>
                  <th>Changes</th>
                  <th>Config</th>
                </tr>
              </thead>
              <tbody>
                {d.alerts.map((a) => (
                  <tr key={a.id} title={a.summary}>
                    <td>
                      {a.as_of}
                      {a.trigger === "replay" && <Tag>replay</Tag>}
                    </td>
                    <td>
                      <Badge kind="stage" value={a.stage} />
                    </td>
                    <td>
                      {a.changed_fields
                        .map((c: any) => `${FIELD_LABEL[c.field] ?? c.field}: ${c.from ?? "new"} → ${c.to}`)
                        .join(" · ")}
                    </td>
                    <td className="mono">{a.config_hash.slice(0, 8)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </>
  );
}
