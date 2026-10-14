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

async function request<T>(method: "GET" | "POST", path: string, params?: Record<string, unknown>, body?: unknown): Promise<T> {
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
  if (!res.ok) throw new Error(`${method} ${path} failed: ${res.status} ${await res.text()}`);
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
