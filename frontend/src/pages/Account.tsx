import { useMutation } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { authApi } from "../api/client";
import { isAdmin, useUser } from "../components/Auth";
import { Input } from "./AuthPages";

const fmt = (iso: string | null) => (iso ? new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" }) : "never");

export function Account() {
  const user = useUser();
  const [pw, setPw] = useState({ current: "", next: "", confirm: "" });
  const change = useMutation({
    mutationFn: () => authApi.changePassword(pw.current, pw.next),
    onSuccess: () => setPw({ current: "", next: "", confirm: "" }),
  });
  const mismatch = pw.confirm !== "" && pw.next !== pw.confirm;
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!mismatch) change.mutate();
  };
  return (
    <section className="account" style={{ display: "flex", flexDirection: "column", gap: 24 }}>
      <header className="page-head">
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <span className="eyebrow">Your profile and password</span>
          <h1>Account</h1>
        </div>
      </header>
      <div className="row-wrap">
        <div className="surface account-card">
          <span className="cap">Profile</span>
          <dl className="kvlist">
            <dt>Name</dt>
            <dd>{user.name}</dd>
            <dt>Email</dt>
            <dd>{user.email}</dd>
            <dt>Role</dt>
            <dd>
              {isAdmin(user) ? "Admin" : "Member"}
              <span className="muted small">
                {" "}
                · {isAdmin(user) ? "runs data jobs, edits the catalog and manages the team" : "views signals and records decisions"}
              </span>
            </dd>
            <dt>Member since</dt>
            <dd>{fmt(user.created_at)}</dd>
          </dl>
        </div>
        <form className="surface account-card" onSubmit={submit}>
          <span className="cap">Change password</span>
          <Input label="Current password" type="password" autoComplete="current-password" required value={pw.current} onChange={(e) => setPw({ ...pw, current: e.target.value })} />
          <Input
            label="New password"
            type="password"
            autoComplete="new-password"
            required
            minLength={10}
            value={pw.next}
            onChange={(e) => setPw({ ...pw, next: e.target.value })}
            hint="At least 10 characters. Other browsers signed in to this account will be signed out."
          />
          <Input label="Confirm new password" type="password" autoComplete="new-password" required value={pw.confirm} onChange={(e) => setPw({ ...pw, confirm: e.target.value })} />
          {mismatch && <p className="auth-error">The new passwords don't match.</p>}
          {change.error && <p className="auth-error" role="alert">{change.error.message}</p>}
          {change.isSuccess && <p className="ok" role="status">Password changed.</p>}
          <button className="btn primary-btn" disabled={change.isPending || mismatch} style={{ alignSelf: "flex-start" }}>
            {change.isPending ? "Saving…" : "Change password"}
          </button>
        </form>
      </div>
    </section>
  );
}
