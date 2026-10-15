import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createContext, useContext, useEffect, type ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { AuthRequired, authApi, UNAUTHORIZED_EVENT, type UserOut } from "../api/client";

const UserContext = createContext<UserOut | null>(null);

export function useUser(): UserOut {
  const u = useContext(UserContext);
  if (!u) throw new Error("useUser outside RequireAuth");
  return u;
}

export const isAdmin = (u: UserOut | null) => u?.role === "admin";

/** Wraps every signed-in screen. No session → the sign-in page (and back here afterwards). */
export function RequireAuth({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const loc = useLocation();
  const me = useQuery({
    queryKey: ["me"],
    queryFn: authApi.me,
    retry: (n, e) => !(e instanceof AuthRequired) && n < 2,
    staleTime: 60_000,
  });
  useEffect(() => {
    const onUnauthorized = () => qc.setQueryData(["me"], null);
    window.addEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
  }, [qc]);

  if (me.isLoading) return <div className="auth-loading">Loading…</div>;
  if (me.error && !(me.error instanceof AuthRequired)) {
    return (
      <div className="auth-loading">
        <span className="error">Can't reach the SocialArb server: {me.error.message}</span>
        <button className="btn" onClick={() => me.refetch()}>Try again</button>
      </div>
    );
  }
  if (!me.data) {
    const next = loc.pathname + loc.search;
    return <Navigate replace to={next && next !== "/" ? `/login?next=${encodeURIComponent(next)}` : "/login"} />;
  }
  return <UserContext.Provider value={me.data}>{children}</UserContext.Provider>;
}

/** Members never see admin-only screens. */
export function AdminOnly({ children }: { children: ReactNode }) {
  const u = useUser();
  return isAdmin(u) ? <>{children}</> : <Navigate replace to="/" />;
}
