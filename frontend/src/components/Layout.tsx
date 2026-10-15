import { NavLink, Outlet } from "react-router-dom";

const NAV = [
  { to: "/", label: "Dashboard", end: true, icon: <><rect x="3" y="3" width="7" height="9" rx="2" /><rect x="14" y="3" width="7" height="5" rx="2" /><rect x="14" y="12" width="7" height="9" rx="2" /><rect x="3" y="16" width="7" height="5" rx="2" /></> },
  { to: "/tickers", label: "Tickers", end: false, icon: <><path d="M3 17l6-6 4 4 8-8" /><path d="M15 7h6v6" /></> },
  { to: "/performance", label: "Performance", end: false, icon: <><path d="M4 20V10" /><path d="M10 20V4" /><path d="M16 20v-7" /><path d="M22 20H2" /></> },
  { to: "/settings", label: "Data & settings", end: false, icon: <><ellipse cx="12" cy="5" rx="8" ry="3" /><path d="M4 5v6c0 1.7 3.6 3 8 3s8-1.3 8-3V5" /><path d="M4 11v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6" /></> },
];

export function Layout() {
  return (
    <div className="shell">
      <nav className="sidebar" aria-label="Main">
        <div className="brand">
          <svg width="28" height="28" viewBox="0 0 28 28" aria-hidden="true">
            <rect width="28" height="28" rx="8" fill="#1a2436" />
            <path d="M6 18 L11 13 L15 16 L22 8" fill="none" stroke="#3987e5" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
            <circle cx="22" cy="8" r="2" fill="#199e70" />
          </svg>
          <span>
            Social<span style={{ color: "#3987e5" }}>Arb</span>
          </span>
        </div>
        <div className="nav">
          {NAV.map((n) => (
            <NavLink key={n.to} to={n.to} end={n.end}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
                {n.icon}
              </svg>
              {n.label}
            </NavLink>
          ))}
        </div>
        <div className="sidebar-foot">
          <span className="demo-chip">Demo data</span>
          <span>Synthetic numbers on real tickers. A review tool, not trading advice.</span>
        </div>
      </nav>
      <main className="content">
        <Outlet />
      </main>
    </div>
  );
}
