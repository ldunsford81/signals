import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { feedApi, type FeedCard, type ReviewIn } from "../api/client";
import { Badge, Tag } from "../components/Badge";

const DECISIONS: { value: ReviewIn["decision"]; label: string }[] = [
  { value: "acted", label: "Acted" },
  { value: "passed", label: "Passed" },
  { value: "exited", label: "Exited" },
];

const pct = (x?: number | null) => (x === null || x === undefined ? "" : `${x >= 0 ? "+" : ""}${(x * 100).toFixed(1)}%`);

function when(iso?: string | null) {
  if (!iso) return "";
  const d = new Date(iso.endsWith("Z") || iso.includes("+") ? iso : `${iso}Z`);
  return d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

function Decision({ card }: { card: FeedCard }) {
  const qc = useQueryClient();
  const [decision, setDecision] = useState<ReviewIn["decision"]>(card.decision as ReviewIn["decision"]);
  const [note, setNote] = useState(card.note ?? "");
  const save = useMutation({
    mutationFn: (body: ReviewIn) => feedApi.review(card.alert_id!, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["feed"] }),
  });
  const dirty = decision !== card.decision || (note || "") !== (card.note || "");

  if (card.alert_id === null || card.alert_id === undefined) {
    return <div className="decision muted">No alert to review for this stage.</div>;
  }
  return (
    <div className="decision">
      <div className="lbl">Your decision</div>
      <div className="seg-row">
        {DECISIONS.map((d) => (
          <button
            key={d.value}
            className={`seg ${decision === d.value ? `on dec-${d.value}` : ""}`}
            onClick={() => setDecision(decision === d.value ? "unreviewed" : d.value)}
          >
            {d.label}
          </button>
        ))}
      </div>
      <textarea placeholder="Note (optional)" value={note} rows={2} onChange={(e) => setNote(e.target.value)} />
      <div className="decision-foot">
        <button className="primary" disabled={!dirty || save.isPending} onClick={() => save.mutate({ decision, note })}>
          {save.isPending ? "Saving…" : "Save"}
        </button>
        <span className="muted">
          {save.isError
            ? <span className="error">Save failed</span>
            : card.decision !== "unreviewed"
              ? `Saved: ${card.decision} · ${when(card.reviewed_at)}`
              : "Unreviewed"}
        </span>
      </div>
    </div>
  );
}

function Changes({ card, priorAsOf }: { card: FeedCard; priorAsOf?: string | null }) {
  if (!priorAsOf) return <span className="muted">First scan: no prior to compare.</span>;
  if (card.changes.length === 0) return <span className="muted">No change since {priorAsOf}.</span>;
  return (
    <span className="changes">
      {card.changes.map((c) => (
        <span key={c.field} className="change">
          {c.label}: {(c.from ?? "—").replace(/_/g, " ")} → <strong>{(c.to ?? "—").replace(/_/g, " ")}</strong>
        </span>
      ))}
    </span>
  );
}

function Card({ card, priorAsOf }: { card: FeedCard; priorAsOf?: string | null }) {
  return (
    <article className="card">
      <div className="card-main">
        <div className="card-head">
          <Badge kind="stage" value={card.stage} />
          <Link to={`/products/${card.product_id}`} className="card-title">
            {card.product}
          </Link>
          {card.is_new ? <Tag title="Entered this stage at this scan">new</Tag> : card.alert_as_of && <span className="muted">in stage since {card.alert_as_of}</span>}
        </div>
        <p className="summary">{card.summary}</p>
        {card.reason && (
          <p className="reason">
            <span className="lbl">Why</span> {card.reason}
          </p>
        )}
        <div className="statuses">
          <span>
            <span className="lbl">Attention</span> <Badge value={card.attention} />
            {card.single_source && <Tag title="Only one attention source is healthy">single_source</Tag>}
          </span>
          <span>
            <span className="lbl">Price</span> <Badge value={card.price} />
            <span className="sub">{pct(card.relative_return)} vs {card.benchmark}</span>
          </span>
          <span>
            <span className="lbl">Retail</span> <Badge value={card.retail} />
          </span>
          <span>
            <span className="lbl">Earnings</span>{" "}
            {card.earnings_status === "unknown" ? (
              <Badge value="unknown" />
            ) : (
              <>
                {card.days_to_earnings} days{card.earnings_projected && <Tag>projected</Tag>}
              </>
            )}
            {card.quarter_closed && <Tag title="Attention from here on mostly lands in the following print">quarter closed</Tag>}
          </span>
        </div>
        <div className="since">
          <span className="lbl">Since last scan</span> <Changes card={card} priorAsOf={priorAsOf} />
        </div>
      </div>
      <Decision key={`${card.alert_id}-${card.decision}-${card.reviewed_at}`} card={card} />
    </article>
  );
}

export function Feed() {
  const { data, isLoading, error } = useQuery({ queryKey: ["feed"], queryFn: feedApi.feed });
  if (isLoading) return <p>Loading…</p>;
  if (error) return <p className="error">{String(error)}</p>;
  if (!data?.scan) return <p>No scan yet. Seed the demo and run a scan (see README).</p>;
  const total = data.groups.reduce((n, g) => n + g.cards.length, 0);
  const counts = data.counts;

  return (
    <section className="feed-layout">
      <div>
        <p className="feed-intro">
          <strong>{total}</strong> product{total === 1 ? "" : "s"} to review as of {data.scan.as_of}
          {total > 0 && (
            <span className="muted">
              {" "}· {counts.exit_review ?? 0} exit · {counts.entry_review ?? 0} entry · {counts.early_recognition ?? 0} early recognition
            </span>
          )}
        </p>
        {data.groups.length === 0 && <p className="muted">Nothing in a reportable stage today.</p>}
        {data.groups.map((g) => (
          <section key={g.company_id} className="company-group">
            <h2>
              {g.company} <span className="mono muted">{g.ticker}</span>
              {g.is_demo && <Tag>demo</Tag>}
            </h2>
            {g.cards.map((c) => (
              <Card key={c.product_id} card={c} priorAsOf={data.prior_as_of} />
            ))}
          </section>
        ))}
      </div>
      <aside className="health-panel">
        <h2>Data gaps</h2>
        <p className="muted small">Products with recent elevated attention whose price, retail or earnings input is unknown. No alerts are written for these.</p>
        {data.health.length === 0 ? (
          <p className="muted">None.</p>
        ) : (
          data.health.map((h) => (
            <div key={h.product_id} className="health-item">
              <div>
                <Link to={`/products/${h.product_id}`}>{h.product}</Link> <span className="mono muted">{h.ticker}</span>
              </div>
              <div className="small">
                attention <Badge value={h.attention} />
              </div>
              <ul>
                {h.unknown_inputs.map((u) => (
                  <li key={u.family}>
                    <strong>{u.family}</strong>: {u.reason}
                  </li>
                ))}
              </ul>
            </div>
          ))
        )}
      </aside>
    </section>
  );
}
