import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import {
  api,
  Conversation,
  ConversationDetail,
  Message,
  Provider,
  streamChat,
} from "../api";

export default function ChatPage() {
  const [providers, setProviders] = useState<Provider[]>([]);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [active, setActive] = useState<ConversationDetail | null>(null);
  const [provider, setProvider] = useState("groq");
  const [model, setModel] = useState("llama-3.3-70b-versatile");
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  const models = useMemoModels(providers, provider);

  const refreshList = useCallback(async () => {
    const list = await api.listConversations();
    setConversations(list);
  }, []);

  useEffect(() => {
    (async () => {
      try {
        const [p, list] = await Promise.all([api.providers(), api.listConversations()]);
        setProviders(p);
        setConversations(list);
        const configured = p.find((x) => x.configured) || p[0];
        if (configured) {
          setProvider(configured.id);
          setModel(configured.models[0]);
        }
      } catch (e: any) {
        setError(e.message || "Failed to load");
      }
    })();
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [active?.messages, streaming]);

  async function openConversation(id: string) {
    const detail = await api.getConversation(id);
    setActive(detail);
    setProvider(detail.provider);
    setModel(detail.model);
    setError(null);
  }

  async function onNew() {
    const conv = await api.createConversation({ provider, model });
    await refreshList();
    await openConversation(conv.id);
  }

  async function onCancel() {
    if (!active) return;
    await api.cancelConversation(active.id);
    if (abortRef.current) abortRef.current.abort();
    await openConversation(active.id);
    await refreshList();
  }

  async function onResume() {
    if (!active) return;
    await api.resumeConversation(active.id);
    await openConversation(active.id);
    await refreshList();
  }

  async function onSend(e?: FormEvent) {
    e?.preventDefault();
    if (!input.trim() || streaming) return;

    let convId = active?.id;
    if (!convId) {
      const conv = await api.createConversation({ provider, model });
      convId = conv.id;
      await refreshList();
      await openConversation(conv.id);
    }

    const userText = input.trim();
    setInput("");
    setStreaming(true);
    setError(null);

    const userMsg: Message = {
      id: `tmp-user-${Date.now()}`,
      conversation_id: convId!,
      role: "user",
      content: userText,
      status: "completed",
      created_at: new Date().toISOString(),
    };
    const assistantMsg: Message = {
      id: `tmp-assistant-${Date.now()}`,
      conversation_id: convId!,
      role: "assistant",
      content: "",
      status: "streaming",
      created_at: new Date().toISOString(),
    };

    setActive((prev) =>
      prev
        ? { ...prev, messages: [...prev.messages, userMsg, assistantMsg] }
        : prev
    );

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      await streamChat(convId!, userText, {
        provider,
        model,
        signal: controller.signal,
        onToken: (token) => {
          setActive((prev) => {
            if (!prev) return prev;
            const messages = [...prev.messages];
            const last = { ...messages[messages.length - 1] };
            last.content += token;
            messages[messages.length - 1] = last;
            return { ...prev, messages };
          });
        },
        onDone: () => {},
        onError: (err) => setError(err),
      });
      await openConversation(convId!);
      await refreshList();
    } catch (err: any) {
      if (err?.name !== "AbortError") setError(err.message || "Stream failed");
    } finally {
      setStreaming(false);
      abortRef.current = null;
    }
  }

  return (
    <div className="layout">
      <aside className="sidebar">
        <div className="sidebar-actions">
          <button className="btn primary" onClick={onNew} style={{ flex: 1 }}>
            New chat
          </button>
        </div>
        <div className="conv-list">
          {conversations.map((c) => (
            <button
              key={c.id}
              className={`conv-item ${active?.id === c.id ? "active" : ""}`}
              onClick={() => openConversation(c.id)}
            >
              <strong>{c.title}</strong>
              <small>
                {c.status} · {c.message_count} msgs · {c.provider}
              </small>
            </button>
          ))}
          {!conversations.length && (
            <div className="empty" style={{ padding: "1rem 0" }}>
              No conversations yet
            </div>
          )}
        </div>
      </aside>

      <section className="main">
        <div className="chat-toolbar">
          <div className="controls">
            <select value={provider} onChange={(e) => {
              const p = e.target.value;
              setProvider(p);
              const meta = providers.find((x) => x.id === p);
              if (meta?.models[0]) setModel(meta.models[0]);
            }}>
              {providers.map((p) => (
                <option key={p.id} value={p.id} disabled={!p.configured}>
                  {p.label}{p.configured ? "" : " (not configured)"}
                </option>
              ))}
            </select>
            <select value={model} onChange={(e) => setModel(e.target.value)}>
              {models.map((m) => (
                <option key={m} value={m}>{m}</option>
              ))}
            </select>
            {active && (
              <span className={`status-pill ${active.status === "cancelled" ? "cancelled" : ""}`}>
                {active.status}
              </span>
            )}
          </div>
          <div className="controls">
            <button className="btn danger" disabled={!active || streaming} onClick={onCancel}>
              Cancel
            </button>
            <button
              className="btn"
              disabled={!active || active.status !== "cancelled"}
              onClick={onResume}
            >
              Resume
            </button>
          </div>
        </div>

        <div className="messages">
          {!active && (
            <div className="empty">
              <h2>Start a conversation</h2>
              <p>
                Multi-turn chat with short context window. Every inference is
                auto-instrumented and shipped to the ingestion pipeline.
              </p>
            </div>
          )}
          {active?.messages.map((m) => (
            <div key={m.id} className={`msg ${m.role}`}>
              {m.content || (m.status === "streaming" ? "…" : "")}
            </div>
          ))}
          {error && <div className="msg system">{error}</div>}
          <div ref={bottomRef} />
        </div>

        <form className="composer" onSubmit={onSend}>
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={
              active?.status === "cancelled"
                ? "Conversation cancelled — resume to continue"
                : "Message Ollive…"
            }
            disabled={streaming || active?.status === "cancelled"}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                onSend();
              }
            }}
          />
          <button className="btn primary" disabled={streaming || !input.trim() || active?.status === "cancelled"}>
            {streaming ? "Streaming…" : "Send"}
          </button>
        </form>
      </section>
    </div>
  );
}

function useMemoModels(providers: Provider[], provider: string) {
  const meta = providers.find((p) => p.id === provider);
  return meta?.models || [];
}