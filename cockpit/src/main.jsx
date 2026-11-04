import React, { Suspense, lazy, useEffect, useState } from "react";
import ReactDOM from "react-dom/client";
import QuantOSCockpit from "./App.jsx";
// Lazy: the reports page pulls in recharts; the dashboard shouldn't pay for it.
const ReportsPage = lazy(() => import("./Reports.jsx"));
const PicksPage = lazy(() => import("./trading/PicksPage.jsx"));
const SpreadsPage = lazy(() => import("./trading/SpreadsPage.jsx"));
const IdeasPage = lazy(() => import("./trading/IdeasPage.jsx"));
const MapPage = lazy(() => import("./trading/MapPage.jsx"));

// Hash routing, no router dependency: "#/reports" is the paper-strategy
// reports page, "#/spreads", "#/picks", "#/ideas" and "#/map/SYMBOL" the trading pages (cockpit/src/trading/,
// the new clean-terminal look), anything else the dashboard. Hash (not path) so nginx's
// SPA fallback and the API's path allowlist are untouched.
function Root() {
  const [hash, setHash] = useState(() => window.location.hash);
  useEffect(() => {
    const onChange = () => { setHash(window.location.hash); window.scrollTo(0, 0); };
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  const route = hash.split("/").slice(0, 2).join("/");      // "#/map/HDFCBANK" -> "#/map"
  const Page = { "#/reports": ReportsPage, "#/picks": PicksPage, "#/spreads": SpreadsPage, "#/ideas": IdeasPage,
                 "#/map": MapPage }[route];
  if (!Page) return <QuantOSCockpit />;
  return (
    <Suspense fallback={<div style={{ background: "#0A0E1A", minHeight: "100vh" }} />}>
      <Page hash={hash} />
    </Suspense>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <Root />
  </React.StrictMode>
);
