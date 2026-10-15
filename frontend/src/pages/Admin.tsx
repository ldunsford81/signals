import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Fragment, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import {
  adminApi,
  api,
  type AnnouncementAdminOut,
  type AnnouncementIn,
  type CompanyIn,
  type CompanyOut,
  type ImportOut,
  type JobOut,
  type ProductIn,
  type ProductOut,
} from "../api/client";
import { Badge, Tag } from "../components/Badge";

const ANN_TYPES = ["new_product", "partnership", "distribution", "negative_event", "other"] as const;
const JOBS = [
  { job: "ingest", label: "Ingest", hint: "fetch every enabled source" },
  { job: "scan", label: "Scan", hint: "statuses, stages and alerts" },
  { job: "daily", label: "Run daily", hint: "backup → ingest → scan → evaluate" },
  { job: "replay", label: "Replay", hint: "every trading day in history (~1 min)" },
  { job: "evaluate", label: "Evaluate", hint: "forward returns for alerts" },
] as const;
type Job = (typeof JOBS)[number]["job"];

const orNull = (v: string) => (v.trim() === "" ? null : v.trim());
const numOrNull = (v: string) => (v.trim() === "" ? null : Number(v));

function useInvalidate() {
  const qc = useQueryClient();
  return () => qc.invalidateQueries();
}

function Field({ label, children, wide }: { label: string; children: ReactNode; wide?: boolean }) {
  return (
    <label className={`field ${wide ? "wide" : ""}`}>
      <span className="lbl">{label}</span>
      {children}
    </label>
  );
}

function ErrorText({ error }: { error: unknown }) {
  return error ? <span className="error small">{error instanceof Error ? error.message : String(error)}</span> : null;
}

// ---- jobs and sources ----------------------------------------------------------------
function summarize(job: Job, r: JobOut): string {
  if (!r.ok) return r.error ?? "failed";
  const x = r.result as any;
  switch (job) {
    case "ingest":
      return x.sources.map((s: any) => `${s.source}: ${s.status} (${s.rows_written})`).join(" · ");
    case "scan":
      return `as of ${x.as_of}: ${x.products} products, ${x.alerts_created} new alerts`;
    case "daily":
      return `scan as of ${x.scan.as_of}: ${x.scan.alerts_created} new alerts · evaluate: ${x.evaluate.outcomes_written} outcomes`;
    case "replay":
      return `${x.start} → ${x.end}: ${x.scans_run} days scanned (${x.scans_skipped} already done), ${x.alerts_created} alerts`;
    case "evaluate":
      return `${x.alerts} alerts, ${x.outcomes_written} outcomes written (${x.outcomes_completed} complete)`;
  }
}

function JobsPanel() {
  const invalidate = useInvalidate();
  const [last, setLast] = useState<{ job: Job; result: JobOut; at: Date } | null>(null);
  const run = useMutation({
    mutationFn: (job: Job) => adminApi.run(job),
    onSuccess: (result, job) => setLast({ job, result, at: new Date() }),
    onSettled: () => invalidate(),
  });
  return (
    <section className="admin-block">
      <h2>Jobs</h2>
      <div className="job-row">
        {JOBS.map((j) => (
          <button key={j.job} className="seg" title={j.hint} disabled={run.isPending} onClick={() => run.mutate(j.job)}>
            {run.isPending && run.variables === j.job ? `${j.label}…` : j.label}
          </button>
        ))}
        <span className="muted small">Same code as the CLI and the scheduled job.</span>
      </div>
      {run.isPending && <p className="muted small">Running {run.variables}… {run.variables === "replay" && "(about a minute)"}</p>}
      <ErrorText error={run.error} />
      {last && (
        <div className={`job-result ${last.result.ok ? "" : "bad"}`}>
          <strong>{last.job}</strong> · {last.at.toLocaleTimeString()} · {summarize(last.job, last.result)}
          <details>
            <summary>Full result</summary>
            <pre>{JSON.stringify(last.result, null, 2)}</pre>
          </details>
        </div>
      )}
    </section>
  );
}

function SourcesPanel() {
  const { data } = useQuery({ queryKey: ["status"], queryFn: api.status });
  return (
    <section className="admin-block" id="sources">
      <h2>Sources</h2>
      <div className="table-wrap">
        <table className="grid compact">
          <thead>
            <tr>
              <th>Source</th>
              <th>Mode</th>
              <th>Scope</th>
              <th>Last run</th>
              <th>Status</th>
              <th className="num">Rows written</th>
              <th>Last good date</th>
              <th>Message</th>
            </tr>
          </thead>
          <tbody>
            {data?.sources.map((s) => (
              <tr key={s.source}>
                <td className="mono">{s.source}</td>
                <td>{s.mode}</td>
                <td>{s.scope ?? "—"}</td>
                <td>{s.last_run_at ? new Date(`${s.last_run_at}Z`).toLocaleString() : "never"}</td>
                <td>
                  <span className={`run-status rs-${s.last_run_status ?? "none"}`}>{s.last_run_status ?? "—"}</span>
                  {s.stale && <Tag title={`No good data within ${s.staleness_limit_days} days`}>stale</Tag>}
                </td>
                <td className="num">{s.rows_written ?? "—"}</td>
                <td>{s.last_good_obs_date ?? "—"}</td>
                <td className="msg">{s.error_message ?? ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="muted small">Modes and scopes are set in config/settings.yaml; credentials go in .env.</p>
    </section>
  );
}

// ---- companies ------------------------------------------------------------------------------
type CompanyForm = Record<string, string | boolean>;

function toForm(c?: CompanyOut): CompanyForm {
  return {
    ticker: c?.ticker ?? "",
    name: c?.name ?? "",
    exchange: c?.exchange ?? "",
    sector: c?.sector ?? "",
    benchmark_ticker: c?.benchmark_ticker ?? "XLY",
    market_cap_usd_m: c?.market_cap_usd_m?.toString() ?? "",
    analyst_count: c?.analyst_count?.toString() ?? "",
    next_earnings_date: c?.next_earnings_date ?? "",
    earnings_date_confirmed: c?.earnings_date_confirmed ?? false,
    fiscal_quarter_end: c?.fiscal_quarter_end ?? "",
    cashtag_exclusions: (c?.cashtag_exclusions ?? []).join(", "),
    is_demo: c?.is_demo ?? false,
    active: c?.active ?? true,
    notes: c?.notes ?? "",
  };
}

function fromForm(f: CompanyForm): CompanyIn {
  const s = (k: string) => String(f[k] ?? "");
  return {
    ticker: s("ticker").trim().toUpperCase(),
    name: s("name").trim(),
    exchange: orNull(s("exchange")),
    sector: orNull(s("sector")),
    benchmark_ticker: s("benchmark_ticker").trim().toUpperCase() || "XLY",
    market_cap_usd_m: numOrNull(s("market_cap_usd_m")),
    analyst_count: numOrNull(s("analyst_count")),
    next_earnings_date: orNull(s("next_earnings_date")),
    earnings_date_confirmed: Boolean(f.earnings_date_confirmed),
    fiscal_quarter_end: orNull(s("fiscal_quarter_end")),
    cashtag_exclusions: s("cashtag_exclusions").split(",").map((x) => x.trim()).filter(Boolean),
    is_demo: Boolean(f.is_demo),
    active: Boolean(f.active),
    notes: orNull(s("notes")),
  };
}

function CompanyEditor({ company, onDone }: { company?: CompanyOut; onDone: () => void }) {
  const invalidate = useInvalidate();
  const [f, setF] = useState<CompanyForm>(toForm(company));
  const save = useMutation({
    mutationFn: () => (company ? adminApi.updateCompany(company.id, fromForm(f)) : adminApi.createCompany(fromForm(f))),
    onSuccess: () => {
      invalidate();
      onDone();
    },
  });
  const text = (k: string, type = "text") => (
    <input type={type} value={String(f[k] ?? "")} onChange={(e) => setF({ ...f, [k]: e.target.value })} />
  );
  const check = (k: string) => <input type="checkbox" checked={Boolean(f[k])} onChange={(e) => setF({ ...f, [k]: e.target.checked })} />;
  return (
    <div className="editor">
      <div className="form-grid">
        <Field label="Ticker">
          <input value={String(f.ticker)} disabled={!!company} onChange={(e) => setF({ ...f, ticker: e.target.value })} />
        </Field>
        <Field label="Name" wide>
          {text("name")}
        </Field>
        <Field label="Exchange">{text("exchange")}</Field>
        <Field label="Sector">{text("sector")}</Field>
        <Field label="Benchmark">{text("benchmark_ticker")}</Field>
        <Field label="Market cap ($m)">{text("market_cap_usd_m", "number")}</Field>
        <Field label="Analysts">{text("analyst_count", "number")}</Field>
        <Field label="Next earnings">{text("next_earnings_date", "date")}</Field>
        <Field label="Confirmed">{check("earnings_date_confirmed")}</Field>
        <Field label="Fiscal quarter end">{text("fiscal_quarter_end", "date")}</Field>
        <Field label="Cashtag exclusions" wide>
          {text("cashtag_exclusions")}
        </Field>
        <Field label="Demo company">{check("is_demo")}</Field>
        <Field label="Active">{check("active")}</Field>
        <Field label="Notes" wide>
          {text("notes")}
        </Field>
      </div>
      <div className="editor-foot">
        <button className="primary" disabled={save.isPending} onClick={() => save.mutate()}>
          {company ? "Save company" : "Add company"}
        </button>
        <button className="seg" onClick={onDone}>
          Cancel
        </button>
        <ErrorText error={save.error} />
        <span className="muted small">
          Earnings dates entered here are used from today on and win over the earnings feed until they pass.
        </span>
      </div>
    </div>
  );
}

function CompaniesPanel({ companies }: { companies: CompanyOut[] }) {
  const [editing, setEditing] = useState<number | "new" | null>(null);
  return (
    <section className="admin-block" id="companies">
      <div className="block-head">
        <h2>Companies</h2>
        <button className="seg" onClick={() => setEditing("new")}>
          + Add company
        </button>
      </div>
      {editing === "new" && <CompanyEditor onDone={() => setEditing(null)} />}
      <div className="table-wrap">
        <table className="grid compact">
          <thead>
            <tr>
              <th>Ticker</th>
              <th>Name</th>
              <th>Sector</th>
              <th>Benchmark</th>
              <th>Next earnings</th>
              <th>Quarter end</th>
              <th>Earnings status</th>
              <th className="num">Products</th>
              <th>Active</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {companies.map((c) => (
              <CompanyRow key={c.id} c={c} open={editing === c.id} toggle={() => setEditing(editing === c.id ? null : c.id)} />
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function CompanyRow({ c, open, toggle }: { c: CompanyOut; open: boolean; toggle: () => void }) {
  const e = c.earnings;
  return (
    <>
      <tr className={e?.needs_date_update ? "flag-row" : ""}>
        <td className="mono">{c.ticker}</td>
        <td>
          {c.name}
          {c.is_demo && <Tag>demo</Tag>}
        </td>
        <td>{c.sector ?? "—"}</td>
        <td className="mono">{c.benchmark_ticker}</td>
        <td>
          {e?.next_earnings_date ?? "—"}
          {e?.confirmed === false && <Tag>projected</Tag>}
        </td>
        <td>{e?.fiscal_quarter_end ?? "—"}</td>
        <td>
          {e?.needs_date_update ? (
            <Badge value="unknown" reason={e.reason} />
          ) : (
            <span className="small">
              {e?.days_to_earnings} days{e?.source === "manual" && <Tag title="Entered in Admin">manual</Tag>}
            </span>
          )}
        </td>
        <td className="num">{c.product_count}</td>
        <td>{c.active ? "yes" : <span className="muted">no</span>}</td>
        <td>
          <button className="link" onClick={toggle}>
            {open ? "Close" : "Edit"}
          </button>
        </td>
      </tr>
      {open && (
        <tr className="editor-row">
          <td colSpan={10}>
            <CompanyEditor company={c} onDone={toggle} />
          </td>
        </tr>
      )}
    </>
  );
}

// ---- products -----------------------------------------------------------------------------------
function ProductEditor({ product, companies, onDone }: { product?: ProductOut; companies: CompanyOut[]; onDone: () => void }) {
  const invalidate = useInvalidate();
  const [companyId, setCompanyId] = useState<number>(product?.company_id ?? companies[0]?.id ?? 0);
  const [name, setName] = useState(product?.name ?? "");
  const [keywords, setKeywords] = useState((product?.keywords ?? []).join(", "));
  const [launched, setLaunched] = useState(product?.launched_on ?? "");
  const [active, setActive] = useState(product?.active ?? true);
  const body = (): ProductIn => ({
    company_id: companyId,
    name: name.trim(),
    keywords: keywords.split(",").map((k) => k.trim()).filter(Boolean),
    launched_on: orNull(launched),
    active,
  });
  const save = useMutation({
    mutationFn: () => (product ? adminApi.updateProduct(product.id, body()) : adminApi.createProduct(body())),
    onSuccess: () => {
      invalidate();
      onDone();
    },
  });
  return (
    <div className="editor">
      <div className="form-grid">
        <Field label="Company">
          <select value={companyId} disabled={!!product} onChange={(e) => setCompanyId(Number(e.target.value))}>
            {companies.map((c) => (
              <option key={c.id} value={c.id}>
                {c.ticker} · {c.name}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Product name" wide>
          <input value={name} disabled={!!product} onChange={(e) => setName(e.target.value)} />
        </Field>
        <Field label="Search keywords (comma separated)" wide>
          <input value={keywords} onChange={(e) => setKeywords(e.target.value)} />
        </Field>
        <Field label="Launched on">
          <input type="date" value={launched} onChange={(e) => setLaunched(e.target.value)} />
        </Field>
        <Field label="Active">
          <input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} />
        </Field>
      </div>
      <div className="editor-foot">
        <button className="primary" disabled={save.isPending || !name.trim()} onClick={() => save.mutate()}>
          {product ? "Save product" : "Add product"}
        </button>
        <button className="seg" onClick={onDone}>
          Cancel
        </button>
        <ErrorText error={save.error} />
        {!product && (
          <span className="muted small">
            The next ingest backfills its full history. In demo mode a new product gets a synthetic rising-attention profile, so
            Run daily shows it flowing through to a stage and an alert.
          </span>
        )}
      </div>
    </div>
  );
}

function ProductsPanel({ companies }: { companies: CompanyOut[] }) {
  const { data } = useQuery({ queryKey: ["admin-products"], queryFn: adminApi.products });
  const [editing, setEditing] = useState<number | "new" | null>(null);
  const [filter, setFilter] = useState("");
  const rows = (data ?? []).filter((p) => !filter || p.ticker === filter);
  return (
    <section className="admin-block">
      <div className="block-head">
        <h2>Products</h2>
        <select value={filter} onChange={(e) => setFilter(e.target.value)}>
          <option value="">all companies</option>
          {companies.map((c) => (
            <option key={c.id} value={c.ticker}>
              {c.ticker}
            </option>
          ))}
        </select>
        <button className="seg" onClick={() => setEditing("new")}>
          + Add product
        </button>
      </div>
      {editing === "new" && <ProductEditor companies={companies} onDone={() => setEditing(null)} />}
      <div className="table-wrap">
        <table className="grid compact">
          <thead>
            <tr>
              <th>Ticker</th>
              <th>Product</th>
              <th>Keywords</th>
              <th>Launched</th>
              <th>Active</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {rows.map((p) => (
              <ProductRow key={p.id} p={p} companies={companies} open={editing === p.id} toggle={() => setEditing(editing === p.id ? null : p.id)} />
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function ProductRow({ p, companies, open, toggle }: { p: ProductOut; companies: CompanyOut[]; open: boolean; toggle: () => void }) {
  return (
    <>
      <tr>
        <td className="mono">{p.ticker}</td>
        <td>
          <Link to={`/tickers/${p.ticker}?product=${p.id}`}>{p.name}</Link>
        </td>
        <td className="small">{p.keywords.join(", ")}</td>
        <td>{p.launched_on ?? "—"}</td>
        <td>{p.active ? "yes" : <span className="muted">no</span>}</td>
        <td>
          <button className="link" onClick={toggle}>
            {open ? "Close" : "Edit"}
          </button>
        </td>
      </tr>
      {open && (
        <tr className="editor-row">
          <td colSpan={6}>
            <ProductEditor product={p} companies={companies} onDone={toggle} />
          </td>
        </tr>
      )}
    </>
  );
}

// ---- announcements ----------------------------------------------------------------------------------
function AnnouncementEditor({ ann, companies, onDone }: { ann?: AnnouncementAdminOut; companies: CompanyOut[]; onDone: () => void }) {
  const invalidate = useInvalidate();
  const { data: products } = useQuery({ queryKey: ["admin-products"], queryFn: adminApi.products });
  const [f, setF] = useState({
    company_id: ann?.company_id ?? companies[0]?.id ?? 0,
    product_id: ann?.product_id ?? null,
    event_date: ann?.event_date ?? new Date().toISOString().slice(0, 10),
    type: (ann?.type ?? "new_product") as AnnouncementIn["type"],
    title: ann?.title ?? "",
    url: ann?.url ?? "",
    notes: ann?.notes ?? "",
  });
  const body = (): AnnouncementIn => ({ ...f, url: orNull(f.url ?? ""), notes: orNull(f.notes ?? "") });
  const save = useMutation({
    mutationFn: () => (ann ? adminApi.updateAnnouncement(ann.id, body()) : adminApi.createAnnouncement(body())),
    onSuccess: () => {
      invalidate();
      onDone();
    },
  });
  const companyProducts = (products ?? []).filter((p) => p.company_id === f.company_id);
  return (
    <div className="editor">
      <div className="form-grid">
        <Field label="Company">
          <select value={f.company_id} onChange={(e) => setF({ ...f, company_id: Number(e.target.value), product_id: null })}>
            {companies.map((c) => (
              <option key={c.id} value={c.id}>
                {c.ticker}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Product">
          <select value={f.product_id ?? ""} onChange={(e) => setF({ ...f, product_id: e.target.value ? Number(e.target.value) : null })}>
            <option value="">whole company</option>
            {companyProducts.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Date">
          <input type="date" value={f.event_date} onChange={(e) => setF({ ...f, event_date: e.target.value })} />
        </Field>
        <Field label="Type">
          <select value={f.type} onChange={(e) => setF({ ...f, type: e.target.value as AnnouncementIn["type"] })}>
            {ANN_TYPES.map((t) => (
              <option key={t} value={t}>
                {t.replace("_", " ")}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Title" wide>
          <input value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} />
        </Field>
        <Field label="URL" wide>
          <input value={f.url ?? ""} onChange={(e) => setF({ ...f, url: e.target.value })} />
        </Field>
      </div>
      <div className="editor-foot">
        <button className="primary" disabled={save.isPending || !f.title.trim()} onClick={() => save.mutate()}>
          {ann ? "Save announcement" : "Add announcement"}
        </button>
        <button className="seg" onClick={onDone}>
          Cancel
        </button>
        <ErrorText error={save.error} />
      </div>
    </div>
  );
}

function AnnouncementsPanel({ companies }: { companies: CompanyOut[] }) {
  const invalidate = useInvalidate();
  const { data } = useQuery({ queryKey: ["admin-announcements"], queryFn: adminApi.announcements });
  const [editing, setEditing] = useState<number | "new" | null>(null);
  const del = useMutation({ mutationFn: adminApi.deleteAnnouncement, onSuccess: () => invalidate() });
  return (
    <section className="admin-block">
      <div className="block-head">
        <h2>Announcements</h2>
        <button className="seg" onClick={() => setEditing("new")}>
          + Add announcement
        </button>
        <span className="muted small">Shown as markers on the Detail charts and in attention components (last 14 days).</span>
      </div>
      {editing === "new" && <AnnouncementEditor companies={companies} onDone={() => setEditing(null)} />}
      <div className="table-wrap">
        <table className="grid compact">
          <thead>
            <tr>
              <th>Date</th>
              <th>Ticker</th>
              <th>Type</th>
              <th>Title</th>
              <th>Scope</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {(data ?? []).map((a) => (
              <Fragment key={a.id}>
                <tr>
                  <td>{a.event_date}</td>
                  <td className="mono">{a.ticker}</td>
                  <td>{a.type.replace("_", " ")}</td>
                  <td>{a.title}</td>
                  <td>{a.product_id ? "product" : "company"}</td>
                  <td className="actions">
                    <button className="link" onClick={() => setEditing(editing === a.id ? null : a.id)}>
                      {editing === a.id ? "Close" : "Edit"}
                    </button>
                    <button
                      className="link danger"
                      onClick={() => window.confirm(`Delete "${a.title}"?`) && del.mutate(a.id)}
                    >
                      Delete
                    </button>
                  </td>
                </tr>
                {editing === a.id && (
                  <tr className="editor-row">
                    <td colSpan={6}>
                      <AnnouncementEditor ann={a} companies={companies} onDone={() => setEditing(null)} />
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

// ---- CSV import ----------------------------------------------------------------------------------------
function CsvImporter({ kind, columns }: { kind: "companies" | "products"; columns: string[] }) {
  const invalidate = useInvalidate();
  const [text, setText] = useState("");
  const [result, setResult] = useState<ImportOut | null>(null);
  const run = useMutation({
    mutationFn: (dry: boolean) => adminApi.importCsv(kind, text, dry),
    onSuccess: (r) => {
      setResult(r);
      if (r.applied) invalidate();
    },
  });
  const onFile = async (file?: File) => {
    if (file) setText(await file.text());
  };
  return (
    <div className="csv-box">
      <h3>{kind === "companies" ? "Companies" : "Products"}</h3>
      <p className="muted small">
        Columns: <code>{columns.join(",")}</code>
        {kind === "products" && " · keywords separated by ; · import companies first"}. Rows are matched on{" "}
        {kind === "companies" ? "ticker" : "ticker + name"} and updated if they exist.
      </p>
      <input type="file" accept=".csv,text/csv" onChange={(e) => onFile(e.target.files?.[0])} />
      <textarea rows={5} placeholder={`${columns.join(",")}\n…`} value={text} onChange={(e) => setText(e.target.value)} />
      <div className="editor-foot">
        <button className="seg" disabled={!text.trim() || run.isPending} onClick={() => run.mutate(true)}>
          Check
        </button>
        <button className="primary" disabled={!text.trim() || run.isPending} onClick={() => run.mutate(false)}>
          Import
        </button>
        <ErrorText error={run.error} />
        {result && result.errors.length === 0 && (
          <span className="small">
            {result.applied ? "Imported" : "Looks good"}: {result.created} new, {result.updated} updated
            {!result.applied && " (nothing saved yet)"}
          </span>
        )}
      </div>
      {result && result.errors.length > 0 && (
        <ul className="error small">
          {result.errors.map((e) => (
            <li key={e.line}>
              line {e.line}: {e.error}
            </li>
          ))}
          <li>Nothing was imported. Fix these rows and try again.</li>
        </ul>
      )}
    </div>
  );
}

function ImportPanel() {
  const { data } = useQuery({ queryKey: ["csv-templates"], queryFn: adminApi.templates });
  if (!data) return null;
  return (
    <section className="admin-block">
      <h2>CSV import</h2>
      <div className="two-col">
        <CsvImporter kind="companies" columns={data.companies} />
        <CsvImporter kind="products" columns={data.products} />
      </div>
    </section>
  );
}

// ---- page ----------------------------------------------------------------------------------------------
export function Admin() {
  const { data: companies } = useQuery({ queryKey: ["admin-companies"], queryFn: adminApi.companies });
  const flagged = (companies ?? []).filter((c) => c.earnings?.needs_date_update && c.active);
  return (
    <section className="admin">
      <header className="page-head" style={{ marginBottom: 20 }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <span className="eyebrow">Jobs, feeds, catalog and imports</span>
          <h1>Data &amp; settings</h1>
        </div>
      </header>
      {flagged.length > 0 && (
        <div className="banner warn flag-banner">
          <strong>Earnings date needs an update</strong>
          <ul>
            {flagged.map((c) => (
              <li key={c.id}>
                <span className="mono">{c.ticker}</span> {c.name}: {c.earnings?.reason}. Products show earnings{" "}
                <em>unknown</em> and cannot reach entry review until it is fixed (Edit below).
              </li>
            ))}
          </ul>
        </div>
      )}
      <JobsPanel />
      <SourcesPanel />
      {companies && (
        <>
          <CompaniesPanel companies={companies} />
          <ProductsPanel companies={companies} />
          <AnnouncementsPanel companies={companies} />
        </>
      )}
      <ImportPanel />
    </section>
  );
}
