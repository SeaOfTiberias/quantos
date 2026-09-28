import React, { Suspense, lazy, useEffect, useState } from "react";
import ReactDOM from "react-dom/client";
import QuantOSCockpit from "./App.jsx";
// Lazy: the reports page pulls in recharts; the dashboard shouldn't pay for it.
const ReportsPage = lazy(() => import("./Reports.jsx"));

// Hash routing, no router dependency: "#/reports" is the paper-strategy
// reports page, anything else the dashboard. Hash (not path) so nginx's
// SPA fallback and the API's path allowlist are untouched.
function Root() {
  const [hash, setHash] = useState(() => window.location.hash);
  useEffect(() => {
    const onChange = () => { setHash(window.location.hash); window.scrollTo(0, 0); };
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  if (hash !== "#/reports") return <QuantOSCockpit />;
  return (
    <Suspense fallback={<div style={{ background: "#0A0E1A", minHeight: "100vh" }} />}>
      <ReportsPage />
    </Suspense>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <Root />
  </React.StrictMode>
);
