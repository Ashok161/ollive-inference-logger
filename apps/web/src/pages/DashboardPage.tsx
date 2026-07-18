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
    return new Date(ts).toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return ts;
  }
}

const tooltipStyle = {
  background: "rgba(255,255,255,0.95)",
  border: "1px solid rgba(16,20,28,0.12)",
  borderRadius: 4,
  fontFamily: "JetBrains Mono, monospace",
  fontSize: 12,
};

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
      <div className="dash-hero">
        <div>
          <h2>Latency. Throughput. Errors.</h2>
          <p>
            Live aggregates from the ingestion pipeline. Every instrumented
            model call shows up here within seconds.
          </p>
        </div>
        <div className="controls">
          <span className="live-dot">
            <i aria-hidden="true" />
            Live · 5s
          </span>
          <label className="field">
            <span>Window</span>
            <select
              value={windowMinutes}
              onChange={(e) => setWindowMinutes(Number(e.target.value))}
            >
              <option value={15}>Last 15m</option>
              <option value={60}>Last 60m</option>
              <option value={180}>Last 3h</option>
              <option value={1440}>Last 24h</option>
            </select>
          </label>
        </div>
      </div>

      {error && <div className="msg system">{error}</div>}

      <div className="kpi-row">
        <div className="kpi">
          <label>Requests / min</label>
          <strong>{metrics?.requests_per_minute ?? "—"}</strong>
        </div>
        <div className="kpi">
          <label>Avg latency</label>
          <strong>
            {metrics ? `${metrics.avg_latency_ms.toFixed(0)}ms` : "—"}
          </strong>
        </div>
        <div className="kpi">
          <label>p95 latency</label>
          <strong>
            {metrics ? `${metrics.p95_latency_ms.toFixed(0)}ms` : "—"}
          </strong>
        </div>
        <div className={`kpi ${metrics && metrics.error_rate > 0 ? "alert" : ""}`}>
          <label>Error rate</label>
          <strong>
            {metrics ? `${(metrics.error_rate * 100).toFixed(1)}%` : "—"}
          </strong>
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
          <strong>
            {metrics ? `${metrics.avg_ttft_ms.toFixed(0)}ms` : "—"}
          </strong>
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
                  <stop offset="0%" stopColor="#1f7a5c" stopOpacity={0.35} />
                  <stop offset="100%" stopColor="#1f7a5c" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke="rgba(16,20,28,0.08)" vertical={false} />
              <XAxis dataKey="label" tick={{ fontSize: 11, fill: "#6b7585" }} />
              <YAxis tick={{ fontSize: 11, fill: "#6b7585" }} />
              <Tooltip contentStyle={tooltipStyle} />
              <Area
                type="monotone"
                dataKey="avg_latency_ms"
                stroke="#1f7a5c"
                fill="url(#lat)"
                name="avg ms"
                strokeWidth={2}
              />
              <Area
                type="monotone"
                dataKey="p95_latency_ms"
                stroke="#e24a1b"
                fillOpacity={0}
                name="p95 ms"
                strokeWidth={1.5}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        <div className="panel">
          <h3>Throughput</h3>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={throughputData}>
              <CartesianGrid stroke="rgba(16,20,28,0.08)" vertical={false} />
              <XAxis dataKey="label" tick={{ fontSize: 11, fill: "#6b7585" }} />
              <YAxis tick={{ fontSize: 11, fill: "#6b7585" }} allowDecimals={false} />
              <Tooltip contentStyle={tooltipStyle} />
              <Bar dataKey="requests" fill="#10141c" radius={[2, 2, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="charts">
        <div className="panel">
          <h3>Errors over time</h3>
          <ResponsiveContainer width="100%" height={220}>
            <AreaChart data={errorData}>
              <CartesianGrid stroke="rgba(16,20,28,0.08)" vertical={false} />
              <XAxis dataKey="label" tick={{ fontSize: 11, fill: "#6b7585" }} />
              <YAxis tick={{ fontSize: 11, fill: "#6b7585" }} allowDecimals={false} />
              <Tooltip contentStyle={tooltipStyle} />
              <Area
                type="monotone"
                dataKey="errors"
                stroke="#c42318"
                fill="rgba(196,35,24,0.12)"
                strokeWidth={2}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        <div className="panel">
          <h3>By provider</h3>
          <div className="provider-list">
            {(metrics?.by_provider || []).map((p) => (
              <div className="provider-row" key={p.provider}>
                <strong>{p.provider}</strong>
                <span>{p.count} req · {p.avg_latency_ms.toFixed(0)}ms</span>
                <span className={p.errors ? "err" : "ok"}>{p.errors} err</span>
              </div>
            ))}
            {!metrics?.by_provider?.length && (
              <div className="sidebar-empty">
                No inference traffic yet — send a chat message.
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="panel">
        <h3>Recent inference events</h3>
        <div className="events">
          {events.map((e) => (
            <div className="event-row" key={e.id}>
              <span className={e.status === "error" ? "err" : "ok"}>
                {e.status}
              </span>
              <span>{Math.round(e.latency_ms)}ms</span>
              <span>
                {e.provider}/{e.model} · {e.input_preview?.slice(0, 48)}
              </span>
              <span>{e.total_tokens} tok</span>
            </div>
          ))}
          {!events.length && (
            <div className="sidebar-empty">Waiting for events…</div>
          )}
        </div>
      </div>
    </div>
  );
}