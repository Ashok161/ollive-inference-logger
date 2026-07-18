import { useEffect, useState } from "react";
import ChatPage from "./pages/ChatPage";
import DashboardPage from "./pages/DashboardPage";

type Tab = "chat" | "dashboard";

export default function App() {
  const [tab, setTab] = useState<Tab>("chat");

  useEffect(() => {
    document.title = tab === "chat" ? "Ollive — Chat" : "Ollive — Observatory";
  }, [tab]);

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand">
          <div className="brand-mark">
            <span className="brand-orb" aria-hidden="true" />
            <h1>Ollive</h1>
          </div>
          <p className="brand-sub">
            Inference observatory for multi-provider LLM traffic — chat, stream,
            and watch every call land in near real time.
          </p>
        </div>
        <nav className="nav" aria-label="Primary">
          <button
            className={tab === "chat" ? "active" : ""}
            onClick={() => setTab("chat")}
          >
            Chat
          </button>
          <button
            className={tab === "dashboard" ? "active" : ""}
            onClick={() => setTab("dashboard")}
          >
            Observatory
          </button>
        </nav>
      </header>
      {tab === "chat" ? <ChatPage /> : <DashboardPage />}
    </div>
  );
}