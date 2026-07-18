import { useEffect, useMemo, useState } from "react";
import ChatPage from "./pages/ChatPage";
import DashboardPage from "./pages/DashboardPage";

type Tab = "chat" | "dashboard";

export default function App() {
  const [tab, setTab] = useState<Tab>("chat");
  const year = useMemo(() => new Date().getFullYear(), []);

  useEffect(() => {
    document.title =
      tab === "chat" ? "Ollive — Chat" : "Ollive — Latency & Errors";
  }, [tab]);

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand">
          <h1>Ollive</h1>
          <span>Inference observatory · multi-provider LLM telemetry</span>
        </div>
        <nav className="nav">
          <button className={tab === "chat" ? "active" : ""} onClick={() => setTab("chat")}>
            Chat
          </button>
          <button
            className={tab === "dashboard" ? "active" : ""}
            onClick={() => setTab("dashboard")}
          >
            Dashboards
          </button>
        </nav>
      </header>
      {tab === "chat" ? <ChatPage /> : <DashboardPage />}
      <footer
        style={{
          textAlign: "center",
          color: "var(--muted)",
          fontSize: "0.75rem",
          padding: "0.75rem",
        }}
      >
        Ollive Inference Logger · {year}
      </footer>
    </div>
  );
}