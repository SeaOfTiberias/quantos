// Page shell for the trading pages: top bar with navigation and the two
// broker-session chips. Each chip opens a small panel with that broker's
// daily login: Fyers = open login, paste the code back (fyers_auth_routes.py);
// ICICI Direct = open login, ICICI posts the token straight to the VM
// (breeze_auth_routes.py), the chip polls until it turns green.
import { useEffect, useRef, useState } from "react";
import { CLOUD_API_URL } from "../App.jsx";
import { CSS, clock } from "./theme.js";

async function getJson(path) {
  try {
    const res = await fetch(`${CLOUD_API_URL}${path}`);
    return res.ok ? await res.json() : null;
  } catch { return null; }
}

async function postJson(path, body) {
  const res = await fetch(`${CLOUD_API_URL}${path}`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: body ? JSON.stringify(body) : undefined,
  });
  const d = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(d.detail || `request failed (${res.status})`);
  return d;
}

function useOutside(ref, onOut) {
  useEffect(() => {
    const h = e => { if (ref.current && !ref.current.contains(e.target)) onOut(); };
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, [ref, onOut]);
}

function Chip({ ok, label, detail, children }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  useOutside(ref, () => setOpen(false));
  return (
    <div ref={ref} style={{ position: "relative" }}>
      <button className={`q-pill ${ok ? "green" : "amber"}`} style={{ cursor: "pointer", background: "transparent" }}
              onClick={() => setOpen(o => !o)} title={detail}>
        <span className="dot" />{label}
      </button>
      {open && <div className="q-pop">{children}</div>}
    </div>
  );
}

function FyersChip() {
  const [st, setSt] = useState(null);
  const [phase, setPhase] = useState("idle");
  const [code, setCode] = useState("");
  const [msg, setMsg] = useState("");
  useEffect(() => {
    let live = true;
    const load = () => getJson("/auth/fyers/status").then(d => { if (live && d) setSt(d); });
    load();
    const id = setInterval(load, 300000);
    return () => { live = false; clearInterval(id); };
  }, []);
  const start = async () => {
    setMsg("");
    try {
      const d = await postJson("/auth/fyers/start");
      window.open(d.auth_url, "_blank", "noopener,noreferrer");
      setPhase("code");
    } catch (e) { setMsg(String(e.message || e)); }
  };
  const complete = async () => {
    try {
      const d = await postJson("/auth/fyers/complete", { code: code.trim() });
      setCode(""); setPhase("idle");
      setMsg(d.agent_restarted ? "Token saved." : `Token saved; agent restart failed (${d.restart_detail}).`);
      setSt(await getJson("/auth/fyers/status"));
    } catch (e) { setMsg(String(e.message || e)); }
  };
  const ok = st?.refreshed_today;
  return (
    <Chip ok={ok} label={`Fyers ${ok ? clock(st.at) : "login"}`} detail="Fyers token">
      <div className="q-label">Fyers token</div>
      <div className="q-sub">{ok ? `Refreshed today at ${clock(st.at)}.` : "Not refreshed today. Fyers tokens expire daily."}</div>
      <div className="q-row" style={{ marginTop: 12 }}>
        <button className="q-btn primary" onClick={start}>Open Fyers login</button>
      </div>
      {phase === "code" && (
        <div className="q-row" style={{ marginTop: 10 }}>
          <input className="q-input" style={{ flex: 1 }} value={code} onChange={e => setCode(e.target.value)}
                 placeholder="Paste the redirect URL or code" />
          <button className="q-btn" disabled={!code.trim()} onClick={complete}>Save</button>
        </div>
      )}
      {msg && <div className="q-sub">{msg}</div>}
    </Chip>
  );
}

function IciciChip() {
  const [st, setSt] = useState(null);
  const [waitingSince, setWaitingSince] = useState(0);
  const [code, setCode] = useState("");
  const [msg, setMsg] = useState("");
  useEffect(() => {
    let live = true;
    const load = () => getJson("/auth/breeze/status?check=true").then(d => { if (live && d) setSt(d); });
    load();
    const id = setInterval(load, 300000);
    return () => { live = false; clearInterval(id); };
  }, []);
  useEffect(() => {
    if (!waitingSince) return undefined;
    let tries = 0;
    const id = setInterval(async () => {
      tries += 1;
      const d = await getJson("/auth/breeze/status");
      // Only a session saved after the click counts (an older one from today would mislead).
      if (d?.created_at && new Date(d.created_at).getTime() > waitingSince) {
        setSt({ ...d, valid: true }); setWaitingSince(0); setMsg("Connected.");
      } else if (tries > 60) { setWaitingSince(0); }
    }, 3000);
    return () => clearInterval(id);
  }, [waitingSince]);
  const start = async () => {
    setMsg("");
    try {
      const d = await postJson("/auth/breeze/start");
      window.open(d.auth_url, "_blank", "noopener,noreferrer");
      setWaitingSince(Date.now() - 5000);
    } catch (e) { setMsg(String(e.message || e)); }
  };
  const paste = async () => {
    try {
      await postJson("/auth/breeze/complete", { code: code.trim() });
      setCode(""); setWaitingSince(0); setMsg("Session saved.");
      setSt(await getJson("/auth/breeze/status?check=true"));
    } catch (e) { setMsg(String(e.message || e)); }
  };
  const ok = st?.valid;
  return (
    <Chip ok={ok} label={`ICICI ${ok ? clock(st.created_at) : "login"}`} detail="ICICI Direct session">
      <div className="q-label">ICICI Direct session</div>
      <div className="q-sub">
        {ok ? `Live, saved at ${clock(st.created_at)}.`
          : "Not connected. ICICI keeps one session at a time; log in each morning."}
      </div>
      <div className="q-row" style={{ marginTop: 12 }}>
        <button className="q-btn primary" onClick={start}>{waitingSince ? "Waiting for login…" : "Log in to ICICI Direct"}</button>
      </div>
      {waitingSince > 0 && (
        <div className="q-row" style={{ marginTop: 10 }}>
          <input className="q-input" style={{ flex: 1 }} value={code} onChange={e => setCode(e.target.value)}
                 placeholder="Only if it doesn't connect: paste the URL" />
          <button className="q-btn" disabled={!code.trim()} onClick={paste}>Save</button>
        </div>
      )}
      {msg && <div className="q-sub">{msg}</div>}
    </Chip>
  );
}

export default function Shell({ active, children }) {
  return (
    <div className="q-app">
      <style>{CSS}</style>
      <header className="q-top">
        <a className="q-brand" href="#/">QUANT<b>OS</b></a>
        <nav className="q-nav">
          <a href="#/spreads" className={active === "spreads" ? "on" : ""}>Spreads</a>
          <a href="#/picks" className={active === "picks" ? "on" : ""}>Options picks</a>
          <a href="#/ideas" className={active === "ideas" ? "on" : ""}>Ideas</a>
          <a href="#/reports">Reports</a>
          <a href="#/">Dashboard</a>
        </nav>
        <div className="q-row q-chips" style={{ marginLeft: "auto" }}>
          <FyersChip />
          <IciciChip />
        </div>
      </header>
      <main className="q-main">{children}</main>
    </div>
  );
}

export { getJson, postJson };
