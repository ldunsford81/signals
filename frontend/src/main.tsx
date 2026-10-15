import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes, useParams } from "react-router-dom";
import { productApi } from "./api/client";
import { AdminOnly, RequireAuth } from "./components/Auth";
import { Layout } from "./components/Layout";
import { Account } from "./pages/Account";
import { Admin } from "./pages/Admin";
import { Alerts } from "./pages/Alerts";
import { Login, Signup } from "./pages/AuthPages";
import { Dashboard } from "./pages/Dashboard";
import { Ticker } from "./pages/Ticker";
import { Watchlist } from "./pages/Watchlist";
import "./styles.css";

const queryClient = new QueryClient({ defaultOptions: { queries: { refetchOnWindowFocus: false } } });

/** Old /products/:id links land on the ticker page with that product selected. */
function ProductRedirect() {
  const { id } = useParams();
  const { data, error } = useQuery({ queryKey: ["product-ticker", id], queryFn: () => productApi.detail(Number(id), 60) });
  if (error) return <p className="error">{String(error)}</p>;
  if (!data) return <p className="muted">Opening…</p>;
  return <Navigate replace to={`/tickers/${data.company.ticker}?product=${id}`} />;
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/signup" element={<Signup />} />
          <Route
            element={
              <RequireAuth>
                <Layout />
              </RequireAuth>
            }
          >
            <Route path="/" element={<Dashboard />} />
            <Route path="/tickers" element={<Watchlist />} />
            <Route path="/tickers/:ticker" element={<Ticker />} />
            <Route path="/performance" element={<Alerts />} />
            <Route
              path="/settings"
              element={
                <AdminOnly>
                  <Admin />
                </AdminOnly>
              }
            />
            <Route path="/account" element={<Account />} />
            <Route path="/products/:id" element={<ProductRedirect />} />
            <Route path="/feed" element={<Navigate replace to="/" />} />
            <Route path="/alerts" element={<Navigate replace to="/performance" />} />
            <Route path="/admin" element={<Navigate replace to="/settings" />} />
            <Route path="*" element={<Navigate replace to="/" />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>,
);
