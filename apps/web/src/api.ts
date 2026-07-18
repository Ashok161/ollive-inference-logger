const API_URL = import.meta.env.VITE_API_URL || "";

export type Provider = {
  id: string;
  label: string;
  models: string[];
  configured: boolean;
};

export type Conversation = {
  id: string;
  title: string;
  status: string;
  provider: string;
  model: string;
  session_id: string;
  cancel_requested: boolean;
  created_at: string;
  updated_at: string;
  message_count: number;
};

export type Message = {
  id: string;
  conversation_id: string;
  role: string;
  content: string;
  status: string;
  created_at: string;
};

export type ConversationDetail = Conversation & { messages: Message[] };

export type MetricsSummary = {
  window_minutes: number;
  total_requests: number;
  success_count: number;
  error_count: number;
  cancelled_count: number;
  error_rate: number;
  avg_latency_ms: number;
  p95_latency_ms: number;
  avg_ttft_ms: number;
  total_tokens: number;
  requests_per_minute: number;
  by_provider: Array<{
    provider: string;
    count: number;
    errors: number;
    avg_latency_ms: number;
  }>;
  by_model: Array<{ model: string; provider: string; count: number; errors: number }>;
  latency_series: Array<{ ts: string; avg_latency_ms: number; p95_latency_ms: number }>;
  throughput_series: Array<{ ts: string; requests: number }>;
  error_series: Array<{ ts: string; errors: number }>;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    ...init,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || res.statusText);
  }
  return res.json();
}

export const api = {
  providers: () => request<Provider[]>("/v1/providers"),
  listConversations: () => request<Conversation[]>("/v1/conversations"),
  createConversation: (body: { title?: string; provider?: string; model?: string }) =>
    request<Conversation>("/v1/conversations", { method: "POST", body: JSON.stringify(body) }),
  getConversation: (id: string) => request<ConversationDetail>(`/v1/conversations/${id}`),
  cancelConversation: (id: string) =>
    request<Conversation>(`/v1/conversations/${id}/cancel`, { method: "POST" }),
  resumeConversation: (id: string) =>
    request<Conversation>(`/v1/conversations/${id}/resume`, { method: "POST" }),
  metrics: (windowMinutes = 60) =>
    request<MetricsSummary>(`/v1/metrics/summary?window_minutes=${windowMinutes}`),
  events: (limit = 40) => request<any[]>(`/v1/inference-events?limit=${limit}`),
};

export async function streamChat(
  conversationId: string,
  message: string,
  opts: {
    provider?: string;
    model?: string;
    onToken: (token: string) => void;
    onDone: () => void;
    onError: (err: string) => void;
    signal?: AbortSignal;
  }
) {
  const res = await fetch(`${API_URL}/v1/conversations/${conversationId}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message,
      provider: opts.provider,
      model: opts.model,
      stream: true,
    }),
    signal: opts.signal,
  });

  if (!res.ok || !res.body) {
    const text = await res.text();
    opts.onError(text || res.statusText);
    throw new Error(text || res.statusText);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() || "";
    for (const part of parts) {
      const line = part.trim();
      if (!line.startsWith("data:")) continue;
      let payload: { type: string; content?: string; message?: string };
      try {
        payload = JSON.parse(line.slice(5).trim());
      } catch {
        continue;
      }
      if (payload.type === "token" && payload.content) {
        opts.onToken(payload.content);
      } else if (payload.type === "done" || payload.type === "cancelled") {
        opts.onDone();
      } else if (payload.type === "error") {
        const msg = payload.message || "Stream error";
        opts.onError(msg);
        await reader.cancel();
        throw new Error(msg);
      }
    }
  }
}