// Thin typed client. Types are generated from the FastAPI OpenAPI schema (npm run gen:api).
import type { components } from "./schema";

type S = components["schemas"];
export type StatusOut = S["StatusOut"];
export type WatchlistOut = S["WatchlistOut"];
export type WatchlistRow = S["WatchlistRow"];
export type JobOut = S["JobOut"];

export interface WatchlistQuery {
  stage?: string;
  attention?: string;
  price?: string;
  retail?: string;
  earnings_window: boolean;
}

async function request<T>(method: "GET" | "POST" | "PUT" | "DELETE", path: string, params?: Record<string, unknown>, body?: unknown): Promise<T> {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params ?? {})) {
    if (v !== undefined && v !== null && v !== "") qs.append(k, String(v));
  }
  const url = qs.toString() ? `${path}?${qs}` : path;
  const res = await fetch(url, {
    method,
    headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    const text = await res.text();
    let detail = text;
    try {
      const j = JSON.parse(text);
      detail = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail ?? j);
    } catch {
      /* not JSON */
    }
    throw new Error(detail || `${method} ${path} failed (${res.status})`);
  }
  return (await res.json()) as T;
}

export const api = {
  status: () => request<StatusOut>("GET", "/api/status"),
  watchlist: (q: WatchlistQuery) => request<WatchlistOut>("GET", "/api/watchlist", { ...q }),
  ingest: () => request<JobOut>("POST", "/api/ingest", undefined, {}),
  scan: () => request<JobOut>("POST", "/api/scan", undefined, {}),
  daily: () => request<JobOut>("POST", "/api/daily", undefined, {}),
};

export type ProductDetail = S["ProductDetailOut"];
export type SourceSeries = S["SourceSeries"];

export const productApi = {
  detail: (id: number, days: number) => request<ProductDetail>("GET", `/api/products/${id}`, { days }),
};

export type FeedOut = S["FeedOut"];
export type FeedCard = S["FeedCard"];
export type ReviewIn = S["ReviewIn"];
export type ReviewOut = S["ReviewOut"];

export const feedApi = {
  feed: () => request<FeedOut>("GET", "/api/feed"),
  review: (alertId: number, body: ReviewIn) => request<ReviewOut>("POST", `/api/alerts/${alertId}/review`, undefined, body),
};

export type PerformanceOut = S["PerformanceOut"];
export type PerformanceGroup = S["PerformanceGroup"];
export type AlertLogOut = S["AlertLogOut"];
export type AlertLogRow = S["AlertLogRow"];
export type AlertDetailOut = S["AlertDetailOut"];

export interface AlertQuery {
  stage?: string;
  trigger?: string;
  config_hash?: string;
  start?: string;
  end?: string;
  limit: number;
}

export const evalApi = {
  performance: (combine: boolean) => request<PerformanceOut>("GET", "/api/evaluation", { combine_triggers: combine }),
  alerts: (q: AlertQuery) => request<AlertLogOut>("GET", "/api/alerts", { ...q }),
  alert: (id: number) => request<AlertDetailOut>("GET", `/api/alerts/${id}`),
  evaluate: () => request<JobOut>("POST", "/api/evaluate", undefined, {}),
};

export type CompanyIn = S["CompanyIn"];
export type CompanyOut = S["CompanyOut"];
export type ProductIn = S["ProductIn"];
export type ProductOut = S["ProductOut"];
export type AnnouncementIn = S["AnnouncementIn"];
export type AnnouncementAdminOut = S["AnnouncementAdminOut"];
export type ImportOut = S["ImportOut"];

export const adminApi = {
  companies: () => request<CompanyOut[]>("GET", "/api/admin/companies"),
  createCompany: (b: CompanyIn) => request<CompanyOut>("POST", "/api/admin/companies", undefined, b),
  updateCompany: (id: number, b: CompanyIn) => request<CompanyOut>("PUT", `/api/admin/companies/${id}`, undefined, b),
  products: () => request<ProductOut[]>("GET", "/api/admin/products"),
  createProduct: (b: ProductIn) => request<ProductOut>("POST", "/api/admin/products", undefined, b),
  updateProduct: (id: number, b: ProductIn) => request<ProductOut>("PUT", `/api/admin/products/${id}`, undefined, b),
  announcements: () => request<AnnouncementAdminOut[]>("GET", "/api/admin/announcements"),
  createAnnouncement: (b: AnnouncementIn) => request<AnnouncementAdminOut>("POST", "/api/admin/announcements", undefined, b),
  updateAnnouncement: (id: number, b: AnnouncementIn) =>
    request<AnnouncementAdminOut>("PUT", `/api/admin/announcements/${id}`, undefined, b),
  deleteAnnouncement: (id: number) => request<{ ok: boolean }>("DELETE", `/api/admin/announcements/${id}`),
  templates: () => request<S["CsvTemplates"]>("GET", "/api/admin/import/templates"),
  importCsv: (kind: "companies" | "products", csv: string, dry_run: boolean) =>
    request<ImportOut>("POST", `/api/admin/import/${kind}`, undefined, { csv, dry_run }),
  run: (job: "ingest" | "scan" | "daily" | "replay" | "evaluate") => request<JobOut>("POST", `/api/${job}`, undefined, {}),
};
