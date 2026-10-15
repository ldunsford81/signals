import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, viewApi, type TickerRow } from "../api/client";
import { isAdmin, useUser } from "../components/Auth";
import { pct } from "../components/chartTheme";
import { ChatterDots, DualSpark, Icon, ICONS, MiniSpark, SectionHead, SignalPill, signalColor } from "../components/Signal";

const longDate = (iso: string) =>
  new Date(`${iso}T12:00:00Z`).toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long", timeZone: "UTC" });

const tickerHref = (r: { ticker: string; product_id: number }) => `/tickers/${r.ticker}?product=${r.product_id}`;

function SignalCard({ r }: { r: TickerRow }) {
  const strength = Math.min(100, Math.round(((r.strength ?? 0) / 3.5) * 100));
  return (
    <Link to={tickerHref(r)} className="sig-card">
      <div className="sig-card-head">
        <div style={{ display: "flex", flexDirection: "column", gap: 2, minWidth: 0 }}>
          <span className="sig-ticker">{r.ticker}</span>
          <span className="sig-sub">
            {r.short_name} · {r.product}
          </span>
        </div>
        <SignalPill stage={r.stage} label={r.label} />
      </div>
      <DualSpark buzz={r.buzz_spark} price={r.price_spark} label={`Product buzz and ${r.ticker} relative to ${r.benchmark}, last 45 days`} />
      <div className="sig-facts">
        <span>
          <b style={{ color: "#6fa4ee" }}>Buzz</b> {r.buzz_ratio ? `${r.buzz_ratio.toFixed(1)}×` : "—"}
          {r.buzz_days ? ` for ${r.buzz_days} days` : ""}
        </span>
        <span>
          <b style={{ color: "#e8875a" }}>Price</b> {pct(r.relative_return)} vs {r.benchmark}
        </span>
        <span>
          <b style={{ color: "#9aa6ba" }}>Chatter</b> {r.retail}
        </span>
      </div>
      <div className="sig-foot">
        <span style={{ flex: "1 1 auto", display: "flex", alignItems: "center", gap: 8 }}>
          Strength
          <span className="meter">
            <span style={{ width: `${strength}%`, background: signalColor(r.stage) }} />
          </span>
        </span>
        <span>{r.earnings_status === "unknown" ? "Earnings date needed" : `Earnings in ${r.days_to_earnings} days`}</span>
        {r.new_today && <span className="chip">New today</span>}
      </div>
    </Link>
  );
}

function BoardRow({ r }: { r: TickerRow }) {
  const active = r.attention === "elevated";
  return (
    <Link to={tickerHref(r)} className="trow" aria-label={`Open ${r.ticker}`}>
      <span className="tk">
        <b>{r.ticker}</b>
        <span>{r.short_name}</span>
      </span>
      <span>
        <SignalPill stage={r.stage} label={r.label} size="sm" />
      </span>
      <span style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <MiniSpark values={r.buzz_spark} active={active} label={`Product buzz trend for ${r.ticker}`} />
        <span className="num-mono" style={{ color: active ? "#8fb6f2" : "#7f8ba3" }}>
          {r.buzz_ratio ? `${r.buzz_ratio.toFixed(1)}×` : "—"}
        </span>
      </span>
      <span className="r num-mono" style={{ color: "#c3cbd8" }}>
        {r.price === "unknown" ? "stale" : pct(r.relative_return)}
      </span>
      <span style={{ fontSize: 13, color: "#c3cbd8" }}>
        <ChatterDots level={r.retail} />
        {r.retail}
      </span>
      <span className="r" style={{ fontSize: 13, color: r.earnings_status === "unknown" ? "#d7b46a" : r.earnings_status === "inside_window" ? "#c3cbd8" : "#7f8ba3" }}>
        {r.earnings_status === "unknown" ? "Needs date" : `${r.days_to_earnings} days`}
      </span>
      <span style={{ display: "flex", justifyContent: "flex-end", color: "#7f8ba3" }}>
        <Icon d={ICONS.chevronRight} size={16} stroke={2} />
      </span>
    </Link>
  );
}

export function Dashboard() {
  const qc = useQueryClient();
  const nav = useNavigate();
  const { data, isLoading, error } = useQuery({ queryKey: ["dashboard"], queryFn: viewApi.dashboard });
  const [showQuiet, setShowQuiet] = useState(false);
  const [q, setQ] = useState("");
  const daily = useMutation({ mutationFn: api.daily, onSettled: () => qc.invalidateQueries() });
  const admin = isAdmin(useUser());

  if (isLoading) return <p className="muted">Loading today's read…</p>;
  if (error) return <p className="error">Can't reach the API: {String(error)}</p>;
  if (!data) return null;
  if (!data.scan) {
    return (
      <section className="surface headline">
        <h1 style={{ margin: 0 }}>No scan yet</h1>
        {admin ? (
          <>
            <p>Seed the demo and run a scan (see the README), or press Run daily.</p>
            <button className="btn primary-btn" onClick={() => daily.mutate()} disabled={daily.isPending}>
              {daily.isPending ? "Running…" : "Run daily"}
            </button>
          </>
        ) : (
          <p>Nothing has been scanned yet. An admin needs to run the daily job.</p>
        )}
      </section>
    );
  }

  const needle = q.trim().toLowerCase();
  const matches = (r: TickerRow) =>
    !needle || r.ticker.toLowerCase().includes(needle) || r.company.toLowerCase().includes(needle) || r.product.toLowerCase().includes(needle);
  const quiet = data.board.filter((r) => r.stage === "none");
  const board = data.board.filter((r) => (showQuiet || needle || r.stage !== "none") && matches(r));
  const k = data.kpis;
  const issues = data.health.issues.length;

  return (
    <>
      <header className="page-head">
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <span className="eyebrow">{longDate(String(data.scan.as_of))} · after the US close</span>
          <h1>Today's read</h1>
        </div>
        <div className="head-actions">
          <form
            className="search"
            role="search"
            onSubmit={(e) => {
              e.preventDefault();
              const hit = data.board.find((r) => r.ticker.toLowerCase() === needle) ?? (board.length === 1 ? board[0] : undefined);
              if (hit) nav(tickerHref(hit));
            }}
          >
            <Icon d={ICONS.search} size={16} stroke={2} />
            <label className="visually-hidden" htmlFor="dash-search">
              Search ticker or product
            </label>
            <input id="dash-search" type="search" placeholder="Search ticker or product" value={q} onChange={(e) => setQ(e.target.value)} />
          </form>
          {issues > 0 && admin ? (
            <Link to="/settings#sources" className="btn warn" title={data.health.issues.map((i) => `${i.source}: ${i.message}`).join("\n")}>
              <span className="dot" style={{ background: "#d7b46a" }} />
              {issues} feed{issues > 1 ? "s" : ""} need a look
            </Link>
          ) : issues > 0 ? (
            <span className="btn warn" style={{ cursor: "default" }} title={data.health.issues.map((i) => `${i.source}: ${i.message}`).join("\n")}>
              <span className="dot" style={{ background: "#d7b46a" }} />
              {issues} feed{issues > 1 ? "s" : ""} need a look
            </span>
          ) : (
            <span className="btn" style={{ cursor: "default" }}>
              <span className="dot" style={{ background: "#199e70" }} />
              All feeds healthy
            </span>
          )}
          {admin && (
            <button className="btn primary-btn" onClick={() => daily.mutate()} disabled={daily.isPending}>
              {daily.isPending ? "Running…" : "Run daily"}
            </button>
          )}
        </div>
      </header>
      {daily.data && !daily.data.ok && <div className="banner error">Run daily failed: {daily.data.error}</div>}

      <section className="surface headline" aria-label="Summary">
        <p>
          {data.headline.map((s, i) => (s.strong ? <strong key={i}>{s.text}</strong> : <span key={i}>{s.text}</span>))}
        </p>
        <div className="kpis">
          <a href="#buy" className="kpi" style={{ boxShadow: "inset 0 2px 0 #199e70" }}>
            <span className="kpi-label">
              <Icon d={ICONS.up} size={16} color="#199e70" /> Entry signals
            </span>
            <span className="kpi-value">
              <b>{k.entry.count}</b>
              <span>{k.entry.new ? `${k.entry.new} new today` : "none new today"}</span>
            </span>
          </a>
          <a href="#buy" className="kpi" style={{ boxShadow: "inset 0 2px 0 #9085e9" }}>
            <span className="kpi-label">
              <Icon d={ICONS.upRight} size={16} color="#9085e9" /> Early movers
            </span>
            <span className="kpi-value">
              <b>{k.early.count}</b>
              <span>price starting to move</span>
            </span>
          </a>
          <a href="#sell" className="kpi" style={{ boxShadow: "inset 0 2px 0 #e66767" }}>
            <span className="kpi-label">
              <Icon d={ICONS.down} size={16} color="#e66767" /> Exit signals
            </span>
            <span className="kpi-value">
              <b>{k.exit.count}</b>
              <span>{k.exit.new ? `${k.exit.new} new today` : "chatter caught up"}</span>
            </span>
          </a>
          <a href="#sell" className="kpi" style={{ boxShadow: "inset 0 2px 0 #64748b" }}>
            <span className="kpi-label">
              <Icon d={ICONS.eye} size={16} color="#94a3b8" /> Watching
            </span>
            <span className="kpi-value">
              <b>{k.watch.count}</b>
              <span>{k.watch.attention_needed ? `+${k.watch.attention_needed} need data` : "on the radar"}</span>
            </span>
          </a>
        </div>
      </section>

      <section className="board" aria-label="Signals to review">
        <div className="board-main" id="buy">
          <SectionHead title={<>Buy-side <span>· entry signals and early movers</span></>} note="Buzz up, price hasn't caught up yet" />
          {data.buy.length === 0 ? (
            <div className="empty-card">No entry signals today.</div>
          ) : (
            <div className="cards">
              {data.buy.map((r) => (
                <SignalCard key={r.ticker} r={r} />
              ))}
            </div>
          )}
        </div>
        <div className="board-side" id="sell">
          <SectionHead title={<>Sell-side <span>· exit signals</span></>} />
          {data.sell.length === 0 ? <div className="empty-card">No exit signals today.</div> : data.sell.map((r) => <SignalCard key={r.ticker} r={r} />)}
          {data.radar.length > 0 && (
            <div className="radar">
              <h3>Also on the radar</h3>
              {data.radar.map((r) => (
                <Link key={`${r.ticker}-${r.kind}`} to={r.kind === "earnings" && admin ? "/settings#companies" : tickerHref(r)}>
                  <span className="mono" style={{ fontWeight: 600 }}>
                    {r.ticker}
                  </span>
                  <span className="note">{r.note}</span>
                  <SignalPill stage={r.stage} label={r.label} size="sm" kind={r.kind === "earnings" || r.kind === "chatter" ? r.kind : undefined} />
                </Link>
              ))}
            </div>
          )}
        </div>
      </section>

      <section aria-label="All tickers" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <SectionHead
          title={
            <>
              All tickers <span>· {needle ? `${board.length} matching` : showQuiet ? `${data.board.length} tickers` : `${data.board.length - quiet.length} with something happening`}</span>
            </>
          }
        >
          {!needle && quiet.length > 0 && (
            <button className="btn" style={{ height: 36 }} onClick={() => setShowQuiet(!showQuiet)}>
              {showQuiet ? "Hide quiet tickers" : `Show ${quiet.length} quiet tickers`}
            </button>
          )}
        </SectionHead>
        <div className="tboard">
          <div className="tboard-inner">
            <div className="trow head">
              <span>Ticker</span>
              <span>Signal</span>
              <span>Product buzz · 45 days</span>
              <span className="r">Price vs benchmark</span>
              <span>Retail chatter</span>
              <span className="r">Earnings</span>
              <span />
            </div>
            {board.map((r) => (
              <BoardRow key={r.ticker} r={r} />
            ))}
            {board.length === 0 && <div className="trow" style={{ color: "#7f8ba3" }}>No tickers match “{q}”.</div>}
          </div>
        </div>
        <p className="section-note" style={{ margin: 0 }}>
          One row per ticker, showing its strongest product. Open a ticker for the reasoning, the charts and the raw numbers;{" "}
          <Link to="/tickers">see every product</Link>.
        </p>
      </section>
    </>
  );
}
