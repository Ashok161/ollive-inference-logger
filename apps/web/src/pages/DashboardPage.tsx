import { useEffect, useState } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api, MetricsSummary } from "../api";

function shortTs(ts: string) {
  try {
    return new Date(ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  } catch {
    return ts;
  }
}

export default function DashboardPage() {
  const [metrics, setMetrics] = useState<MetricsSummary | null>(null);
  const [events, setEvents] = useState<any[]>([]);
  const [windowMinutes, setWindowMinutes] = useState(60);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    async function load() {
      try {
        const [m, e] = await Promise.all([
          api.metrics(windowMinutes),
          api.events(40),
        ]);
        if (!alive) return;
        setMetrics(m);
        setEvents(e);
        setError(null);
      } catch (err: any) {
        if (alive) setError(err.message || "Failed to load metrics");
      }
    }
    load();
    const id = setInterval(load, 5000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [windowMinutes]);

  const latencyData =
    metrics?.latency_series.map((d) => ({
      ...d,
      label: shortTs(d.ts),
    })) || [];
  const throughputData =
    metrics?.throughput_series.map((d) => ({
      ...d,
      label: shortTs(d.ts),
    })) || [];
  const errorData =
    metrics?.error_series.map((d) => ({
      ...d,
      label: shortTs(d.ts),
    })) || [];

  return (
    <div className="dashboard">
      <div className="chat-toolbar" style={{ border: "1px solid var(--line)", borderRadius: 18 }}>
        <div>
          <h2 style={{ margin: 0, fontFamily: "var(--font-display)" }}>
            Latency · Throughput · Errors
          </h2>
          <p style={{ margin: "0.25rem 0 0", color: "var(--muted)" }}>
            Live view over inference events (auto-refresh 5s)
          </p>
        </div>
        <select
          value={windowMinutes}
          onChange={(e) => setWindowMinutes(Number(e.target.value))}
        >
          <option value={15}>Last 15m</option>
          <option value={60}>Last 60m</option>
          <option value={180}>Last 3h</option>
          <option value={1440}>Last 24h</option>
        </select>
      </div>

      {error && <div className="msg system">{error}</div>}

      <div className="kpi-row">
        <div className="kpi">
          <label>Requests / min</label>
          <strong>{metrics?.requests_per_minute ?? "—"}</strong>
        </div>
        <div className="kpi">
          <label>Avg latency</label>
          <strong>{metrics ? `${metrics.avg_latency_ms.toFixed(0)} ms` : "—"}</strong>
        </div>
        <div className="kpi">
          <label>p95 latency</label>
          <strong>{metrics ? `${metrics.p95_latency_ms.toFixed(0)} ms` : "—"}</strong>
        </div>
        <div className="kpi">
          <label>Error rate</label>
          <strong>{metrics ? `${(metrics.error_rate * 100).toFixed(1)}%` : "—"}</strong>
        </div>
      </div>

      <div className="kpi-row">
        <div className="kpi">
          <label>Total requests</label>
          <strong>{metrics?.total_requests ?? "—"}</strong>
        </div>
        <div className="kpi">
          <label>Errors</label>
          <strong>{metrics?.error_count ?? "—"}</strong>
        </div>
        <div className="kpi">
          <label>Avg TTFT</label>
          <strong>{metrics ? `${metrics.avg_ttft_ms.toFixed(0)} ms` : "—"}</strong>
        </div>
        <div className="kpi">
          <label>Tokens</label>
          <strong>{metrics?.total_tokens ?? "—"}</strong>
        </div>
      </div>

      <div className="charts">
        <div className="panel">
          <h3>Latency</h3>
          <ResponsiveContainer width="100%" height={220}>
            <AreaChart data={latencyData}>
              <defs>
                <linearGradient id="lat" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#0b6e4f" stopOpacity={0.35} />
                  <stop offset="100%" stopColor="#0b6e4f" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke="rgba(20,32,26,0.08)" vertical={false} />
              <XAxis dataKey="label" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip />
              <Area
                type="monotone"
                dataKey="avg_latency_ms"
                stroke="#0b6e4f"
                fill="url(#lat)"
                name="avg ms"
              />
              <Area
                type="monotone"
                dataKey="p95_latency_ms"
                stroke="#1aa37a"
                fillOpacity={0}
                name="p95 ms"
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        <div className="panel">
          <h3>Throughput</h3>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={throughputData}>
              <CartesianGrid stroke="rgba(20,32,26,0.08)" vertical={false} />
              <XAxis dataKey="label" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
              <Tooltip />
              <Bar dataKey="requests" fill="#0b6e4f" radius={[6, 6, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="charts">
        <div className="panel">
          <h3>Errors over time</h3>
          <ResponsiveContainer width="100%" height={220}>
            <AreaChart data={errorData}>
              <CartesianGrid stroke="rgba(20,32,26,0.08)" vertical={false} />
              <XAxis dataKey="label" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
              <Tooltip />
              <Area
                type="monotone"
                dataKey="errors"
                stroke="#b42318"
                fill="rgba(180,35,24,0.15)"
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        <div className="panel">
          <h3>By provider</h3>
          <div className="events">
            {(metrics?.by_provider || []).map((p) => (
              <div className="event-row" key={p.provider}>
                <span>{p.provider}</span>
                <span>{p.count} req</span>
                <span>{p.avg_latency_ms.toFixed(0)} ms avg</span>
                <span className={p.errors ? "err" : "ok"}>{p.errors} err</span>
              </div>
            ))}
            {!metrics?.by_provider?.length && (
              <div className="msg system">No inference traffic yet — send a chat message.</div>
            )}
          </div>
        </div>
      </div>

      <div className="panel">
        <h3>Recent inference events</h3>
        <div className="events">
          {events.map((e) => (
            <div className="event-row" key={e.id}>
              <span className={e.status === "error" ? "err" : "ok"}>{e.status}</span>
              <span>{Math.round(e.latency_ms)}ms</span>
              <span>
                {e.provider}/{e.model} · {e.input_preview?.slice(0, 48)}
              </span>
              <span>{e.total_tokens} tok</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}