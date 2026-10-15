import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { feedApi, viewApi, type ReviewIn, type TickerOut } from "../api/client";
import { isAdmin, useUser } from "../components/Auth";
import { C, pct, toT } from "../components/chartTheme";
import { Icon, ICONS, SignalPill, STAGE_LABEL } from "../components/Signal";
import { TimeChart, type Marker } from "../components/TimeChart";
import { DetailBody } from "./Detail";

const shortDate = (iso?: string | null) =>
  iso ? new Date(`${iso}T12:00:00Z`).toLocaleDateString(undefined, { day: "numeric", month: "short", timeZone: "UTC" }) : "—";
const money = (m?: number | null) => (m ? (m >= 1000 ? `$${(m / 1000).toFixed(1)}B` : `$${Math.round(m)}M`) : null);

function Decision({ data }: { data: TickerOut }) {
  const qc = useQueryClient();
  const d = data.decision!;
  const [choice, setChoice] = useState<ReviewIn["decision"]>(d.decision as ReviewIn["decision"]);
  const [note, setNote] = useState(d.note ?? "");
  const save = useMutation({
    mutationFn: () => feedApi.review(d.alert_id!, { decision: choice, note }),
    onSuccess: () => qc.invalidateQueries(),
  });
  if (!d.alert_id) {
    return (
      <div className="surface decide">
        <span className="cap">Your call</span>
        <p className="muted" style={{ margin: 0 }}>
          No entry or exit signal to review for this product today. Decisions attach to signals.
        </p>
      </div>
    );
  }
  const dirty = choice !== d.decision || note !== (d.note ?? "");
  return (
    <form className="surface decide" onSubmit={(e) => (e.preventDefault(), save.mutate())}>
      <span className="cap">Your call</span>
      <div className="decide-grid">
        {(["acted", "passed", "exited"] as const).map((v) => (
          <button key={v} type="button" className={choice === v ? `on-${v}` : ""} aria-pressed={choice === v} onClick={() => setChoice(choice === v ? "unreviewed" : v)}>
            {v[0].toUpperCase() + v.slice(1)}
          </button>
        ))}
      </div>
      <label>
        Note
        <textarea rows={2} placeholder="Why you acted or passed" value={note} onChange={(e) => setNote(e.target.value)} />
      </label>
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <button type="submit" className="btn primary-btn" style={{ height: 36 }} disabled={!dirty || save.isPending}>
          {save.isPending ? "Saving…" : "Save"}
        </button>
        <span className="small muted">
          {save.isError
            ? "Save failed"
            : d.decision !== "unreviewed"
              ? `Saved: ${d.decision}`
              : `Logged against the ${shortDate(String(d.alert_as_of))} signal`}
        </span>
      </div>
    </form>
  );
}

export function Ticker() {
  const { ticker = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const productId = params.get("product") ? Number(params.get("product")) : null;
  const [days, setDays] = useState(60);
  const [open, setOpen] = useState(false);
  const { data, isLoading, error, isFetching } = useQuery({
    queryKey: ["ticker", ticker, productId, days],
    queryFn: () => viewApi.ticker(ticker, productId, days),
    placeholderData: keepPreviousData,
  });

  if (isLoading) return <p className="muted">Loading {ticker}…</p>;
  if (error) return <p className="error">{String(error)}</p>;
  if (!data) return null;
  const co = data.company;
  const sig = data.signal;
  const meta = [co.name, co.sector, `compared with ${co.benchmark}`, money(co.market_cap_usd_m) && `${money(co.market_cap_usd_m)} market cap`, co.analyst_count && `${co.analyst_count} analysts`]
    .filter(Boolean)
    .join(" · ");

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 24, opacity: isFetching ? 0.7 : 1 }}>
      <Link to="/" className="back">
        <Icon d={ICONS.chevronLeft} size={14} stroke={2.2} /> Dashboard
      </Link>

      <header className="ticker-head">
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          <div className="ticker-title">
            <h1>{co.ticker}</h1>
            {sig && <SignalPill stage={sig.stage} label={sig.label} size="lg" />}
            {sig?.signal_start_date && <span className="chip">Buzz since {shortDate(String(sig.signal_start_date))}</span>}
            {co.is_demo && <span className="chip">Fictional</span>}
          </div>
          <span className="ticker-meta">{meta}</span>
        </div>
      </header>

      {!sig ? (
        <p className="muted">This product hasn't been scanned yet. It appears after the next daily run.</p>
      ) : (
        <TickerBody data={data} days={days} setDays={setDays} open={open} setOpen={setOpen} setProduct={(id) => setParams({ product: String(id) })} />
      )}
    </div>
  );
}

function TickerBody({
  data,
  days,
  setDays,
  open,
  setOpen,
  setProduct,
}: {
  data: TickerOut;
  days: number;
  setDays: (n: number) => void;
  open: boolean;
  setOpen: (b: boolean) => void;
  setProduct: (id: number) => void;
}) {
  const sig = data.signal!;
  const t = data.tiles as any;
  const e = data.earnings as any;
  const admin = isAdmin(useUser());
  const ch = data.chart!;
  const co = data.company;
  const asOf = toT(String(data.scan!.as_of));
  const xDomain: [number, number] = [toT(String(ch.window_start)), asOf];

  const markers: Marker[] = [];
  if (sig.signal_start_date) markers.push({ t: toT(String(sig.signal_start_date)), label: "Signal start", strong: true });
  data.announcements.forEach((a, i) => markers.push({ t: toT(String(a.event_date)), label: `A${i + 1}` }));
  const buzzRows = ch.buzz.map((p) => ({
    t: toT(String(p.date)),
    value: p.value,
    band: p.low !== null && p.low !== undefined && p.high !== null && p.high !== undefined ? ([Math.max(0, p.low), p.high] as [number, number]) : undefined,
  }));
  const priceRows = ch.price_rel.map((p) => ({ t: toT(String(p.date)), value: p.value }));
  const fmtPct = (v: number) => `${v > 0 ? "+" : ""}${v.toFixed(1)}%`;

  const timeline = [
    ...data.detail.alerts.filter((a) => a.trigger !== "replay").slice(0, 5).map((a) => ({
      date: String(a.as_of),
      text: `${STAGE_LABEL[a.stage] ?? a.stage}${a.prior_stage && a.prior_stage !== a.stage ? ` (was ${STAGE_LABEL[a.prior_stage] ?? a.prior_stage})` : " opened"}`,
    })),
    ...data.announcements.map((a, i) => ({ date: String(a.event_date), text: `A${i + 1} · ${a.title}` })),
  ]
    .sort((a, b) => b.date.localeCompare(a.date))
    .slice(0, 7);

  const win = e.window as [number, number];
  const scaleMax = 140;
  const buzzSub = t.buzz.seasonal
    ? "matches the same weeks last year"
    : t.buzz.raw === "unknown"
      ? t.buzz.reason ?? "no healthy source"
      : t.buzz.raw === "elevated"
        ? `above normal for ${t.buzz.days} days · ${t.buzz.sources_ok} of ${t.buzz.sources_total} sources agree${t.buzz.single_source ? " (single source)" : ""}`
        : "in its normal range";
  const priceSub =
    t.price.raw === "unknown"
      ? t.price.reason
      : `${t.price.anchor === "signal_start" ? `since the signal started (${shortDate(t.price.base_date)} close)` : "over the last 20 sessions"} · volume ${t.price.volume_ratio ? `${t.price.volume_ratio.toFixed(1)}×` : "n/a"}`;

  return (
    <>
      <section className="row-wrap">
        <div className="surface verdict">
          <p>{sig.verdict}</p>
          <div className="checks">
            {sig.checks.map((c) => (
              <span key={c.label} className={`check ${c.ok ? "" : "no"}`}>
                <Icon d={c.ok ? ICONS.check : ICONS.cross} size={14} stroke={3} color={c.ok ? "#199e70" : "#5b6b85"} />
                {c.label}
              </span>
            ))}
          </div>
        </div>
        <Decision key={`${data.decision?.alert_id}-${data.decision?.decision}`} data={data} />
      </section>

      <section className="tiles" aria-label="The three signals">
        <div className="surface tile">
          <span className="tile-top">
            Product buzz <span className={`pill sm ${t.buzz.raw === "elevated" ? "pill-entry" : "pill-watch"}`} style={t.buzz.raw === "elevated" ? { color: "#8fb6f2", background: "rgba(57,135,229,0.16)" } : undefined}>{t.buzz.status}</span>
          </span>
          <span className="tile-value" style={{ color: "#8fb6f2" }}>
            {t.buzz.ratio ? `${t.buzz.ratio.toFixed(1)}×` : "—"}
          </span>
          <span className="tile-sub">{buzzSub}</span>
        </div>
        <div className="surface tile">
          <span className="tile-top">
            Price vs {t.price.benchmark ?? co.benchmark} <span className="pill sm pill-watch">{t.price.status}</span>
          </span>
          <span className="tile-value" style={{ color: "#e8875a" }}>
            {t.price.raw === "unknown" ? "—" : pct(t.price.relative_return)}
          </span>
          <span className="tile-sub">{priceSub}</span>
        </div>
        <div className="surface tile">
          <span className="tile-top">
            Retail chatter <span className={`pill sm ${t.chatter.raw === "quiet" ? "pill-watch" : "pill-warn"}`}>{t.chatter.status}</span>
          </span>
          <span className="tile-value">{t.chatter.ratio ? `${t.chatter.ratio.toFixed(1)}×` : "—"}</span>
          <span className="tile-sub">
            {t.chatter.raw === "unknown" ? t.chatter.reason : `“${co.ticker} stock” searches and $${co.ticker} posts vs their normal level`}
          </span>
        </div>
      </section>

      <section className="row-wrap" style={{ alignItems: "flex-start" }}>
        <figure className="surface chart-card">
          <figcaption>
            <span style={{ display: "flex", flexDirection: "column", gap: 2 }}>
              <span className="chart-title">{sig.side === "sell" ? "The stock has caught up with the buzz" : "Buzz vs the stock"}</span>
              <span className="chart-sub">
                Last {days} days · {data.product.name}
              </span>
            </span>
            <span style={{ display: "flex", gap: 6 }}>
              {[60, 120, 365].map((n) => (
                <button key={n} className={`seg ${n === days ? "on" : ""}`} onClick={() => setDays(n)}>
                  {n === 365 ? "1 year" : `${n} days`}
                </button>
              ))}
            </span>
          </figcaption>
          <TimeChart
            title="Product buzz"
            subtitle={ch.buzz_source === "social_mentions" ? "social mentions, 7-day average" : "search interest, 7-day average"}
            data={buzzRows}
            series={[{ key: "value", label: "Product buzz", color: C.series1, width: 2.4 }]}
            band={{ key: "band", label: "Normal range" }}
            markers={markers}
            xDomain={xDomain}
            syncId="ticker"
            height={200}
            showXAxis={false}
          />
          <TimeChart
            title={`${co.ticker} vs ${ch.benchmark}`}
            subtitle="relative return since the anchor"
            data={priceRows}
            series={[{ key: "value", label: `${co.ticker} vs ${ch.benchmark}`, color: C.series2, width: 2.2 }]}
            markers={markers}
            hlines={[
              { y: 0, label: "", color: "#2a3445" },
              { y: ch.early_move * 100, label: `+${Math.round(ch.early_move * 100)}% = early move`, color: "#8a5a44" },
            ]}
            xDomain={xDomain}
            syncId="ticker"
            height={140}
            yFormat={fmtPct}
          />
        </figure>

        <aside className="side">
          <div className="surface side-card">
            <h3>Next earnings</h3>
            {e.status === "unknown" ? (
              <>
                <span className="big-date">
                  <b>Needs a date</b>
                </span>
                <span className="small muted">{e.reason}</span>
                {admin && (
                  <Link to="/settings#companies" className="small">
                    Update it in Data &amp; settings
                  </Link>
                )}
              </>
            ) : (
              <>
                <span className="big-date">
                  <b>{shortDate(e.next_date)}</b>
                  <span className="muted small">
                    in {e.days} days{e.projected ? " · projected" : " · confirmed"}
                  </span>
                </span>
                <div className="window-bar" role="img" aria-label={`${e.days} days out; the entry window is ${win[0]} to ${win[1]} days`}>
                  <span className="win" style={{ left: `${(win[0] / scaleMax) * 100}%`, width: `${((win[1] - win[0]) / scaleMax) * 100}%` }} />
                  <span className="mark" style={{ left: `${(Math.min(e.days, scaleMax) / scaleMax) * 100}%` }} />
                </div>
                <span className="small muted">
                  {e.status === "inside_window" ? "Inside" : "Outside"} the {Math.round(win[0] / 7)}–{Math.round(win[1] / 7)} week entry window
                  {e.quarter_end &&
                    (e.days_left_in_quarter > 0
                      ? ` · quarter closes ${shortDate(e.quarter_end)} (${e.days_left_in_quarter} days left)`
                      : " · reporting quarter already closed")}
                </span>
              </>
            )}
          </div>

          {data.products.length > 1 && (
            <div className="surface side-card prod-list">
              <h3>Products</h3>
              {data.products.map((p) => (
                <button key={p.id} className={p.id === data.product.id ? "current" : ""} onClick={() => setProduct(p.id)}>
                  <span>{p.name}</span>
                  <SignalPill stage={p.stage} label={p.label} size="sm" />
                </button>
              ))}
            </div>
          )}

          <div className="surface side-card">
            <h3>Timeline</h3>
            <div className="timeline">
              {timeline.length === 0 && <span className="small muted">Nothing yet.</span>}
              {timeline.map((x, i) => (
                <div key={i}>
                  <time>{shortDate(x.date)}</time>
                  <span>{x.text}</span>
                </div>
              ))}
            </div>
          </div>
        </aside>
      </section>

      <section className="drill">
        <button className="btn" style={{ alignSelf: "flex-start" }} aria-expanded={open} onClick={() => setOpen(!open)}>
          <Icon d={open ? ICONS.chevronUp : ICONS.chevronDown} size={14} />
          {open ? "Hide all the numbers" : "Show all the numbers"}
        </button>
        {open && (
          <div className="drill-body detail">
            <DetailBody d={data.detail} days={days} setDays={setDays} />
          </div>
        )}
      </section>
    </>
  );
}
