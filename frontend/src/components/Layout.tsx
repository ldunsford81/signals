import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { NavLink, Outlet } from "react-router-dom";
import { api } from "../api/client";

function localTime(iso?: string | null) {
  if (!iso) return "—";
  const d = new Date(iso.endsWith("Z") || iso.includes("+") ? iso : `${iso}Z`);
  return d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export function Layout() {
  const qc = useQueryClient();
  const status = useQuery({ queryKey: ["status"], queryFn: api.status });
  const daily = useMutation({
    mutationFn: api.daily,
    onSettled: () => qc.invalidateQueries(),
  });
  const s = status.data;
  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">Trend Monitor</div>
        <nav>
          <NavLink to="/" end>
            Watchlist
          </NavLink>
          <NavLink to="/feed">Review feed</NavLink>
        </nav>
        <div className="asof">
          {s?.as_of ? (
            <>
              As of <strong>{s.as_of}</strong> (US session) · scanned {localTime(s.latest_scan?.finished_at)} local · config{" "}
              <code>{s.config_hash.slice(0, 8)}</code>
            </>
          ) : (
            "No scan yet"
          )}
        </div>
        <button onClick={() => daily.mutate()} disabled={daily.isPending}>
          {daily.isPending ? "Running…" : "Run daily"}
        </button>
      </header>
      {s?.demo_mode && (
        <div className="banner demo">
          Demo data — all numbers are synthetic{s.demo_anchor_date ? `, anchored to ${s.demo_anchor_date}` : ""}. No source is live.
        </div>
      )}
      {s && s.warnings.length > 0 && (
        <div className="banner warn">
          <strong>Data health:</strong>
          <ul>
            {s.warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </div>
      )}
      {daily.data && !daily.data.ok && <div className="banner error">Run daily failed: {daily.data.error}</div>}
      {status.error && <div className="banner error">API unreachable: {String(status.error)}</div>}
      <main>
        <Outlet />
      </main>
    </div>
  );
}
