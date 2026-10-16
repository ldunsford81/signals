import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useId, useState, type FormEvent, type ReactNode } from "react";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router-dom";
import { authApi, type UserOut } from "../api/client";
import { Brand } from "../components/Layout";
import { StoryChart, StoryList } from "../components/SignalStory";

/** Only same-site paths are honoured as a post-sign-in destination. */
function safeNext(next: string | null): string {
  return next && next.startsWith("/") && !next.startsWith("//") ? next : "/";
}

function AuthCard({ title, sub, children }: { title: string; sub?: ReactNode; children: ReactNode }) {
  return (
    <div className="landing">
      <header className="landing-head">
        <Brand />
        <h2>Product buzz, stock price and retail chatter, side by side.</h2>
        <p>
          SocialArb follows attention on consumer products, compares it with the company's stock and with retail chatter about
          the ticker, and flags when they drift apart.
        </p>
      </header>
      <section className="landing-story" aria-label="How the signals work">
        <StoryChart />
        <StoryList />
        <p className="landing-foot">A review tool, not trading advice · socialarb.trade</p>
      </section>
      <main className="landing-form">
        <div className="auth-card">
          <div className="auth-title">
            <h1>{title}</h1>
            {sub && <p>{sub}</p>}
          </div>
          {children}
        </div>
      </main>
    </div>
  );
}

export function Input({ label, hint, ...props }: { label: string; hint?: string } & React.InputHTMLAttributes<HTMLInputElement>) {
  const id = useId();
  return (
    <div className="auth-field">
      <label htmlFor={id}>{label}</label>
      <input id={id} aria-describedby={hint ? `${id}-hint` : undefined} {...props} />
      {hint && <small id={`${id}-hint`}>{hint}</small>}
    </div>
  );
}

function useSignedIn() {
  const qc = useQueryClient();
  const nav = useNavigate();
  const [params] = useSearchParams();
  return (u: UserOut) => {
    qc.clear();
    qc.setQueryData(["me"], u);
    nav(safeNext(params.get("next")), { replace: true });
  };
}

export function Login() {
  const [params] = useSearchParams();
  const status = useQuery({ queryKey: ["auth-status"], queryFn: authApi.status });
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const done = useSignedIn();
  const login = useMutation({ mutationFn: () => authApi.login(email, password), onSuccess: done });

  if (status.data && !status.data.has_users) return <Navigate replace to="/signup" />;
  const submit = (e: FormEvent) => {
    e.preventDefault();
    login.mutate();
  };
  const canSignUp = status.data && status.data.signup_mode !== "closed";
  return (
    <AuthCard title="Sign in" sub="Welcome back. Sign in to see today's signals.">
      <form className="auth-form" onSubmit={submit}>
        <Input label="Email" type="email" autoComplete="email" required autoFocus value={email} onChange={(e) => setEmail(e.target.value)} />
        <Input label="Password" type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
        {login.error && <p className="auth-error" role="alert">{login.error.message}</p>}
        <button className="btn primary-btn auth-submit" disabled={login.isPending}>
          {login.isPending ? "Signing in…" : "Sign in"}
        </button>
      </form>
      <div className="auth-alt">
        {canSignUp && (
          <span>
            Have an invite? <Link to={`/signup${params.get("next") ? `?next=${encodeURIComponent(params.get("next")!)}` : ""}`}>Create an account</Link>
          </span>
        )}
        <span className="muted">Forgot your password? Ask an admin to reset it.</span>
      </div>
    </AuthCard>
  );
}

export function Signup() {
  const [params] = useSearchParams();
  const status = useQuery({ queryKey: ["auth-status"], queryFn: authApi.status });
  const [form, setForm] = useState({ name: "", email: "", password: "", invite: params.get("invite") ?? "" });
  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, [k]: e.target.value });
  const done = useSignedIn();
  const signup = useMutation({
    mutationFn: () =>
      authApi.signup({ name: form.name, email: form.email, password: form.password, invite_code: form.invite.trim() || null }),
    onSuccess: done,
  });

  if (status.isLoading) return <div className="auth-loading">Loading…</div>;
  if (status.error) return <AuthCard title="Can't reach SocialArb"><p className="auth-error">{status.error.message}</p></AuthCard>;
  const s = status.data!;
  const owner = s.signup_mode === "owner";
  if (s.signup_mode === "closed") {
    return (
      <AuthCard title="Sign-up is closed" sub="Ask an admin to create your account.">
        <div className="auth-alt"><Link to="/login">Back to sign in</Link></div>
      </AuthCard>
    );
  }
  const submit = (e: FormEvent) => {
    e.preventDefault();
    signup.mutate();
  };
  return (
    <AuthCard
      title={owner ? "Set up SocialArb" : "Create your account"}
      sub={owner ? "No one has signed up yet. This first account becomes the owner, with access to data jobs, the catalog and the team." : s.invite_required ? "You need an invite code from an admin." : undefined}
    >
      <form className="auth-form" onSubmit={submit}>
        <Input label="Name" autoComplete="name" required autoFocus value={form.name} onChange={set("name")} maxLength={80} />
        <Input label="Email" type="email" autoComplete="email" required value={form.email} onChange={set("email")} />
        <Input
          label="Password"
          type="password"
          autoComplete="new-password"
          required
          minLength={10}
          value={form.password}
          onChange={set("password")}
          hint="At least 10 characters."
        />
        {s.invite_required && (
          <Input label="Invite code" required value={form.invite} onChange={set("invite")} placeholder="XXXXX-XXXXX-XXXXX" className="mono" autoComplete="off" />
        )}
        {signup.error && <p className="auth-error" role="alert">{signup.error.message}</p>}
        <button className="btn primary-btn auth-submit" disabled={signup.isPending}>
          {signup.isPending ? "Creating account…" : owner ? "Create owner account" : "Create account"}
        </button>
      </form>
      {!owner && (
        <div className="auth-alt">
          <span>
            Already have an account? <Link to="/login">Sign in</Link>
          </span>
        </div>
      )}
    </AuthCard>
  );
}
