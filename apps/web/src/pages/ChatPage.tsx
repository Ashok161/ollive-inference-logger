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
  const [model, setModel] = useState("llama-3.1-8b-instant");
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const messagesRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const streamConvIdRef = useRef<string | null>(null);
  const stickToBottomRef = useRef(true);

  const models = providers.find((p) => p.id === provider)?.models || [];

  const refreshList = useCallback(async () => {
    const list = await api.listConversations();
    setConversations(list);
  }, []);

  useEffect(() => {
    (async () => {
      try {
        const [p, list] = await Promise.all([
          api.providers(),
          api.listConversations(),
        ]);
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
    if (!stickToBottomRef.current) return;
    const el = messagesRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [active?.messages, streaming]);

  async function openConversation(id: string) {
    if (streaming && streamConvIdRef.current && streamConvIdRef.current !== id) {
      setError("Stop or wait for the current reply before switching chats.");
      return;
    }
    const detail = await api.getConversation(id);
    setActive(detail);
    setProvider(detail.provider);
    const available =
      providers.find((p) => p.id === detail.provider)?.models || models;
    setModel(
      available.includes(detail.model) ? detail.model : available[0] || detail.model
    );
    setError(null);
    stickToBottomRef.current = true;
  }

  async function onNew() {
    if (streaming) {
      setError("Stop or wait for the current reply before starting a new chat.");
      return;
    }
    const conv = await api.createConversation({ provider, model });
    await refreshList();
    await openConversation(conv.id);
  }

  async function onCancel() {
    if (!active) return;
    const id = active.id;
    await api.cancelConversation(id);
    if (abortRef.current) abortRef.current.abort();
    streamConvIdRef.current = null;
    setStreaming(false);
    await openConversation(id);
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
    stickToBottomRef.current = true;
    streamConvIdRef.current = convId!;

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
      prev && prev.id === convId
        ? { ...prev, messages: [...prev.messages, userMsg, assistantMsg] }
        : prev
    );

    const controller = new AbortController();
    abortRef.current = controller;
    let failed = false;

    try {
      await streamChat(convId!, userText, {
        provider,
        model,
        signal: controller.signal,
        onToken: (token) => {
          setActive((prev) => {
            if (!prev || prev.id !== streamConvIdRef.current) return prev;
            const messages = [...prev.messages];
            const last = { ...messages[messages.length - 1] };
            last.content += token;
            messages[messages.length - 1] = last;
            return { ...prev, messages };
          });
        },
        onDone: () => {},
        onError: (err) => {
          failed = true;
          setError(err);
        },
      });
      if (streamConvIdRef.current === convId && !failed) {
        await openConversation(convId!);
        await refreshList();
      }
    } catch (err: any) {
      if (err?.name !== "AbortError") {
        setError(err.message || "Stream failed");
        if (streamConvIdRef.current === convId) {
          try {
            await openConversation(convId!);
            await refreshList();
          } catch {
            /* ignore */
          }
        }
      }
    } finally {
      if (streamConvIdRef.current === convId) {
        streamConvIdRef.current = null;
      }
      setStreaming(false);
      abortRef.current = null;
    }
  }

  const cancelled = active?.status === "cancelled";
  const visibleMessages =
    active?.messages.filter((m) => m.role !== "system") || [];
  const showEmpty = !active || visibleMessages.length === 0;

  return (
    <div className="layout">
      <aside className="sidebar">
        <div className="sidebar-actions">
          <button className="btn primary" onClick={onNew} disabled={streaming}>
            New conversation
          </button>
        </div>
        <div className="sidebar-label">History</div>
        <div className="conv-list">
          {conversations.map((c) => (
            <button
              key={c.id}
              className={`conv-item ${active?.id === c.id ? "active" : ""}`}
              onClick={() => openConversation(c.id)}
              disabled={streaming && streamConvIdRef.current !== c.id}
            >
              <strong>{c.title}</strong>
              <small>
                {c.status} · {c.message_count} · {c.provider}
              </small>
            </button>
          ))}
          {!conversations.length && (
            <div className="sidebar-empty">No conversations yet</div>
          )}
        </div>
      </aside>

      <section className="main">
        <div className="chat-toolbar">
          <div className="controls">
            <label className="field">
              <span>Provider</span>
              <select
                value={provider}
                onChange={(e) => {
                  const p = e.target.value;
                  setProvider(p);
                  const meta = providers.find((x) => x.id === p);
                  if (meta?.models[0]) setModel(meta.models[0]);
                }}
              >
                {providers.map((p) => (
                  <option key={p.id} value={p.id} disabled={!p.configured}>
                    {p.label}
                    {p.configured ? "" : " — offline"}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>Model</span>
              <select value={model} onChange={(e) => setModel(e.target.value)}>
                {models.map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
              </select>
            </label>
            {active && (
              <span
                className={`status-tag ${cancelled ? "cancelled" : ""}`}
                style={{ alignSelf: "end", marginBottom: 2 }}
              >
                {streaming ? "streaming" : active.status}
              </span>
            )}
          </div>
          <div className="controls">
            <button
              className="btn danger"
              disabled={!active || cancelled}
              onClick={onCancel}
              aria-label={streaming ? "Stop generation" : "Cancel conversation"}
            >
              {streaming ? "Stop" : "Cancel"}
            </button>
            <button
              className="btn ghost"
              disabled={!active || !cancelled || streaming}
              onClick={onResume}
            >
              Resume
            </button>
          </div>
        </div>

        <div
          className="messages"
          ref={messagesRef}
          onScroll={() => {
            const el = messagesRef.current;
            if (!el) return;
            stickToBottomRef.current =
              el.scrollHeight - el.scrollTop - el.clientHeight < 80;
          }}
        >
          <div className={`messages-inner ${showEmpty ? "is-empty" : ""}`}>
            {showEmpty && (
              <div className="empty-stage">
                <p className="wordmark">Ollive</p>
                <h2>
                  {active
                    ? "Type below to start this thread."
                    : "Ask anything. Watch every inference."}
                </h2>
                <p>
                  Multi-turn chat with a short context window. Each reply is
                  auto-instrumented — latency, tokens, and errors stream into
                  the observatory.
                </p>
              </div>
            )}
            {visibleMessages.map((m) => (
              <div
                key={m.id}
                className={`msg ${m.role} ${
                  m.status === "streaming" ||
                  (streaming && m.id.startsWith("tmp-assistant"))
                    ? "streaming"
                    : ""
                } ${m.status === "error" ? "error" : ""}`}
              >
                <div className="msg-meta">
                  {m.role === "user"
                    ? "You"
                    : m.status === "error"
                      ? "Assistant · error"
                      : "Assistant"}
                </div>
                <div className="msg-body">{m.content}</div>
              </div>
            ))}
            {error && <div className="msg system">{error}</div>}
            <div className="sr-only" aria-live="polite">
              {streaming ? "Assistant is responding" : ""}
            </div>
          </div>
        </div>

        <div className="composer-wrap">
          <form className="composer" onSubmit={onSend}>
            <textarea
              value={input}
              aria-label="Message"
              onChange={(e) => setInput(e.target.value)}
              placeholder={
                cancelled
                  ? "Cancelled — resume this thread to continue"
                  : "Message Ollive…"
              }
              disabled={streaming || cancelled}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  onSend();
                }
              }}
            />
            {streaming ? (
              <button
                type="button"
                className="btn danger"
                onClick={onCancel}
                aria-label="Stop generation"
              >
                Stop
              </button>
            ) : (
              <button
                className="btn primary"
                disabled={!input.trim() || cancelled}
              >
                Send
              </button>
            )}
          </form>
        </div>
      </section>
    </div>
  );
}