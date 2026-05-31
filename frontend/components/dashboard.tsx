"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  Area,
  AreaChart,
  CartesianGrid
} from "recharts";

import {
  API_BASE,
  AnomalyItem,
  EventItem,
  HeatmapResponse,
  Metrics,
  RunStatus,
  SessionItem,
  fetchDashboard,
  fetchRunStatus
} from "@/lib/api";

type DashboardState = {
  metrics: Metrics;
  funnel: { run_id: string | null; steps: { name: string; count: number }[] };
  heatmap: HeatmapResponse;
  events: EventItem[];
  anomalies: AnomalyItem[];
  sessions: SessionItem[];
};

function formatPercent(value: number) {
  return `${Math.round(value * 1000) / 10}%`;
}

function formatSeconds(value: number | null | undefined) {
  if (!value) return "0m";
  const minutes = Math.round(value / 60);
  return `${minutes}m`;
}

function timeOnly(value: string) {
  return new Intl.DateTimeFormat("en-IN", {
    hour: "2-digit",
    minute: "2-digit"
  }).format(new Date(value));
}

function Skeleton() {
  return (
    <div className="flex h-screen w-full items-center justify-center bg-background text-on-surface">
      <div className="flex flex-col items-center gap-4">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
        <p className="font-label-caps text-label-caps text-on-surface-variant">Loading Intelligence...</p>
      </div>
    </div>
  );
}

export default function Dashboard() {
  const [state, setState] = useState<DashboardState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [starting, setStarting] = useState(false);
  const [runStatus, setRunStatus] = useState<RunStatus | null>(null);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);

  async function load(runId = selectedRunId) {
    setRefreshing(true);
    try {
      setState(await fetchDashboard(runId));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Dashboard fetch failed");
    } finally {
      setRefreshing(false);
    }
  }

  async function pollRun(runId: string) {
    let latest: RunStatus | null = null;
    for (let attempt = 0; attempt < 120; attempt += 1) {
      latest = await fetchRunStatus(runId);
      setRunStatus(latest);
      if (!["queued", "queued_no_worker", "running"].includes(latest.status)) {
        break;
      }
      await new Promise((resolve) => window.setTimeout(resolve, 2000));
    }

    if (!latest) return;
    if (latest.status === "completed") {
      setSelectedRunId(runId);
      await load(runId);
    }
    if (latest.status === "failed") {
      setError(latest.error || "Ingest run failed");
    }
  }

  async function startRun() {
    setStarting(true);
    setError(null);
    try {
      const response = await fetch(`${API_BASE}/ingest/runs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          store_id: "ST1008",
          auto_start: true,
          detector_mode: "synthetic" // Explicitly send if wanted, backend now forces it anyway
        })
      });
      if (!response.ok) {
        throw new Error(`Start run failed with ${response.status}`);
      }
      const created = (await response.json()) as { run_id: string; status: string };
      setRunStatus({
        run_id: created.run_id,
        status: created.status,
        processed_frames: 0,
        events: 0,
        started_at: new Date().toISOString(),
        finished_at: null,
        error: null,
        config: {}
      });
      await pollRun(created.run_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Start run failed");
    } finally {
      setStarting(false);
    }
  }

  useEffect(() => {
    load(null);
    const id = window.setInterval(() => load(selectedRunId), 10000);
    return () => window.clearInterval(id);
  }, [selectedRunId]);

  const conversionLine = useMemo(() => {
    if (!state) return [];
    return state.sessions
      .filter((session) => !session.is_staff)
      .slice(0, 16)
      .reverse()
      .map((session, index) => ({
        name: `${index + 1}`,
        conversion: session.matched_invoice ? 1 : 0,
        dwell: Math.round((session.dwell_seconds || 0) / 60)
      }));
  }, [state]);

  if (!state) {
    return <Skeleton />;
  }

  const { metrics, funnel, heatmap, events, anomalies, sessions } = state;

  const funnelMax = Math.max(...funnel.steps.map((s) => s.count), 1);
  const entered = funnel.steps.find((s) => s.name === "entered")?.count || 0;
  const browsed = funnel.steps.find((s) => s.name === "browsed")?.count || 0;
  const checkout = funnel.steps.find((s) => s.name === "checkout_visit")?.count || 0;
  const purchased = funnel.steps.find((s) => s.name === "purchased")?.count || 0;
  
  const heatmapColors = ["bg-red-500", "bg-orange-500", "bg-yellow-500", "bg-emerald-500", "bg-cyan-500", "bg-purple-500"];

  return (
    <div className="font-body-lg text-body-lg flex h-screen overflow-hidden bg-background text-on-surface">
      {/* Top Navigation (Mobile) */}
      <nav className="md:hidden fixed top-0 w-full z-50 bg-background/80 backdrop-blur-xl flex items-center justify-between px-container-padding h-20 shadow-2xl shadow-primary/5 border-b border-white/10">
        <div className="font-display-md text-xl font-bold">Store Intelligence</div>
        <div className="flex gap-4">
          <span className="material-symbols-outlined text-primary">notifications</span>
          <span className="material-symbols-outlined text-primary">settings</span>
        </div>
      </nav>

      {/* Side Navigation (Desktop) */}
      <aside className="hidden md:flex flex-col py-6 gap-y-4 bg-surface-container-lowest/50 backdrop-blur-md text-secondary border-r border-white/10 h-full w-sidebar-width fixed left-0 top-0">
        <div className="px-6 mb-4 animate-fade-in-up opacity-0" style={{animationDelay: "0ms", opacity: 1}}>
          <h1 className="font-headline-lg text-headline-lg text-primary">Brigade Bangalore</h1>
          <p className="font-label-caps text-label-caps text-on-surface-variant mt-1 flex items-center gap-2">
            <span className={`w-2 h-2 rounded-full ${runStatus && runStatus.status === "running" ? "bg-amber-400 animate-pulse" : "bg-primary animate-pulse"}`}></span> 
            Live Status: {runStatus ? runStatus.status : "Completed"}
          </p>
        </div>
        <div className="flex-1 px-4 space-y-2 animate-fade-in-up opacity-0 delay-100" style={{animationDelay: "100ms", opacity: 1}}>
          <a className="flex items-center gap-3 px-4 py-3 rounded-lg text-primary bg-primary/10 border-l-4 border-primary font-label-caps text-label-caps hover:bg-surface-container-high transition-colors group" href="#">
            <span className="material-symbols-outlined group-hover:translate-x-1 transition-transform">dashboard</span>
            <span>Overview</span>
          </a>
          <a className="flex items-center gap-3 px-4 py-3 rounded-lg text-on-surface-variant hover:bg-white/5 hover:text-on-surface font-label-caps text-label-caps hover:bg-surface-container-high transition-colors group" href="#">
            <span className="material-symbols-outlined group-hover:translate-x-1 transition-transform">inventory_2</span>
            <span>Inventory</span>
          </a>
          <a className="flex items-center gap-3 px-4 py-3 rounded-lg text-on-surface-variant hover:bg-white/5 hover:text-on-surface font-label-caps text-label-caps hover:bg-surface-container-high transition-colors group" href="#">
            <span className="material-symbols-outlined group-hover:translate-x-1 transition-transform">group</span>
            <span>Traffic</span>
          </a>
          <a className="flex items-center gap-3 px-4 py-3 rounded-lg text-on-surface-variant hover:bg-white/5 hover:text-on-surface font-label-caps text-label-caps hover:bg-surface-container-high transition-colors group" href="#">
            <span className="material-symbols-outlined group-hover:translate-x-1 transition-transform">distance</span>
            <span>Heatmaps</span>
          </a>
          <a className="flex items-center gap-3 px-4 py-3 rounded-lg text-on-surface-variant hover:bg-white/5 hover:text-on-surface font-label-caps text-label-caps hover:bg-surface-container-high transition-colors group" href="#">
            <span className="material-symbols-outlined group-hover:translate-x-1 transition-transform">assessment</span>
            <span>Reports</span>
          </a>
        </div>
        <div className="px-6 mb-6 animate-fade-in-up opacity-0 delay-200" style={{animationDelay: "200ms", opacity: 1}}>
          <button className="w-full py-3 bg-white/5 border border-white/10 rounded-lg text-on-surface font-label-caps text-label-caps hover:bg-white/10 transition-colors">
            View Global Map
          </button>
        </div>
      </aside>

      {/* Main Content Canvas */}
      <main className="flex-1 ml-0 md:ml-[260px] pt-24 md:pt-6 px-container-padding pb-24 md:pb-6 overflow-y-auto">
        {/* Header Actions */}
        <div className="hidden md:flex justify-between items-center mb-8 animate-fade-in-up opacity-0" style={{animationDelay: "0ms", opacity: 1}}>
          <div className="flex items-center gap-4">
            <h2 className="font-headline-lg text-headline-lg text-on-surface">Store Intelligence</h2>
            {error && <span className="text-sm text-error bg-error/10 px-2 py-1 rounded">{error}</span>}
          </div>
          <div className="flex gap-4">
            <button 
              onClick={() => load()} 
              disabled={refreshing}
              className="px-6 py-2 border border-outline rounded-lg text-on-surface hover:bg-white/5 transition-colors font-label-caps text-label-caps flex items-center gap-2"
            >
              <span className={`material-symbols-outlined text-[16px] ${refreshing ? "animate-spin" : ""}`}>refresh</span>
              Refresh
            </button>
            <button 
              onClick={startRun}
              disabled={starting}
              className="px-6 py-2 bg-[linear-gradient(110deg,#10b981,45%,#6ffbbe,55%,#03b5d3)] bg-[length:200%_100%] animate-shimmer text-black rounded-lg font-label-caps text-label-caps hover:opacity-90 transition-opacity font-bold flex items-center gap-2 disabled:opacity-50"
            >
              <span className="material-symbols-outlined text-[16px]">play_arrow</span>
              {starting ? "Processing" : "Start Run"}
            </button>
          </div>
        </div>

        {/* KPI Row */}
        <div className="grid grid-cols-2 md:grid-cols-5 gap-gutter mb-gutter animate-fade-in-up opacity-0 delay-100" style={{animationDelay: "100ms", opacity: 1}}>
          <div className="glass-card rounded-xl p-[20px] hover-glow transition-all duration-300 border-t-primary/50 hover:border-t-primary hover:shadow-[0_-5px_15px_-5px_rgba(78,222,163,0.3)] group">
            <div className="flex justify-between items-start mb-2">
              <span className="font-label-caps text-label-caps text-on-surface-variant">Footfall</span>
              <span className="material-symbols-outlined text-primary transition-transform duration-300 group-hover:scale-125" style={{fontVariationSettings: "'FILL' 1"}}>person</span>
            </div>
            <div className="font-display-md text-display-md text-on-surface">{metrics.footfall.toLocaleString()}</div>
            <div className="mt-4 h-1 w-full bg-surface-container-high rounded-full overflow-hidden">
              <div className="h-full bg-primary" style={{width: '100%'}}></div>
            </div>
          </div>
          
          <div className="glass-card rounded-xl p-[20px] hover-glow transition-all duration-300 border-t-secondary/50 hover:border-t-secondary hover:shadow-[0_-5px_15px_-5px_rgba(76,215,246,0.3)] group">
            <div className="flex justify-between items-start mb-2">
              <span className="font-label-caps text-label-caps text-on-surface-variant">Conversion</span>
              <span className="material-symbols-outlined text-secondary transition-transform duration-300 group-hover:scale-125" style={{fontVariationSettings: "'FILL' 1"}}>shopping_cart</span>
            </div>
            <div className="font-display-md text-display-md text-on-surface">{formatPercent(metrics.conversion_rate)}</div>
            <div className="mt-4 h-1 w-full bg-surface-container-high rounded-full overflow-hidden">
              <div className="h-full bg-secondary" style={{width: `${Math.min(100, metrics.conversion_rate * 100)}%`}}></div>
            </div>
          </div>

          <div className="glass-card rounded-xl p-[20px] hover-glow transition-all duration-300 border-t-tertiary/50 hover:border-t-tertiary hover:shadow-[0_-5px_15px_-5px_rgba(255,176,205,0.3)] group">
            <div className="flex justify-between items-start mb-2">
              <span className="font-label-caps text-label-caps text-on-surface-variant">Invoices</span>
              <span className="material-symbols-outlined text-tertiary transition-transform duration-300 group-hover:scale-125" style={{fontVariationSettings: "'FILL' 1"}}>receipt</span>
            </div>
            <div className="font-display-md text-display-md text-on-surface">{metrics.pos_invoices}</div>
            <div className="mt-4 h-1 w-full bg-surface-container-high rounded-full overflow-hidden">
              <div className="h-full bg-tertiary" style={{width: '80%'}}></div>
            </div>
          </div>

          <div className="glass-card rounded-xl p-[20px] hover-glow transition-all duration-300 border-t-yellow-400/50 hover:border-t-yellow-400 hover:shadow-[0_-5px_15px_-5px_rgba(250,204,21,0.3)] group">
            <div className="flex justify-between items-start mb-2">
              <span className="font-label-caps text-label-caps text-on-surface-variant">Avg Dwell</span>
              <span className="material-symbols-outlined text-yellow-400 transition-transform duration-300 group-hover:scale-125" style={{fontVariationSettings: "'FILL' 1"}}>schedule</span>
            </div>
            <div className="font-display-md text-display-md text-on-surface">{formatSeconds(metrics.avg_dwell_seconds)}</div>
            <div className="mt-4 h-1 w-full bg-surface-container-high rounded-full overflow-hidden">
              <div className="h-full bg-yellow-400" style={{width: '60%'}}></div>
            </div>
          </div>

          <div className="glass-card rounded-xl p-[20px] hover-glow transition-all duration-300 border-t-orange-400/50 hover:border-t-orange-400 hover:shadow-[0_-5px_15px_-5px_rgba(251,146,60,0.3)] group">
            <div className="flex justify-between items-start mb-2">
              <span className="font-label-caps text-label-caps text-on-surface-variant">Anomalies</span>
              <span className="material-symbols-outlined text-orange-400 transition-transform duration-300 group-hover:scale-125" style={{fontVariationSettings: "'FILL' 1"}}>warning</span>
            </div>
            <div className="font-display-md text-display-md text-on-surface">{metrics.anomaly_count}</div>
            <div className="mt-4 h-1 w-full bg-surface-container-high rounded-full overflow-hidden">
              <div className="h-full bg-orange-400" style={{width: metrics.anomaly_count > 0 ? '40%' : '0%'}}></div>
            </div>
          </div>
        </div>

        {/* Charts Row */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-gutter mb-gutter animate-fade-in-up opacity-0 delay-200" style={{animationDelay: "200ms", opacity: 1}}>
          <div className="glass-card rounded-xl p-[20px] h-64">
            <h3 className="font-label-caps text-label-caps text-on-surface-variant mb-4">Customer Funnel</h3>
            <div className="flex flex-col gap-3 h-full pb-6 justify-end">
              <div className="flex items-center gap-4">
                <span className="w-20 text-right font-mono-data text-mono-data text-on-surface-variant">Entered</span>
                <div className="flex-1 h-6 bg-surface-container-highest rounded">
                  <div className="h-full bg-gradient-to-r from-emerald-400 to-teal-500 rounded" style={{ width: `${(entered / funnelMax) * 100}%` }}></div>
                </div>
                <span className="w-12 font-mono-data text-mono-data">{entered}</span>
              </div>
              <div className="flex items-center gap-4">
                <span className="w-20 text-right font-mono-data text-mono-data text-on-surface-variant">Browsed</span>
                <div className="flex-1 h-6 bg-surface-container-highest rounded">
                  <div className="h-full bg-gradient-to-r from-cyan-400 to-blue-500 rounded" style={{ width: `${(browsed / funnelMax) * 100}%` }}></div>
                </div>
                <span className="w-12 font-mono-data text-mono-data">{browsed}</span>
              </div>
              <div className="flex items-center gap-4">
                <span className="w-20 text-right font-mono-data text-mono-data text-on-surface-variant">Checkout</span>
                <div className="flex-1 h-6 bg-surface-container-highest rounded">
                  <div className="h-full bg-gradient-to-r from-fuchsia-400 to-purple-500 rounded" style={{ width: `${(checkout / funnelMax) * 100}%` }}></div>
                </div>
                <span className="w-12 font-mono-data text-mono-data">{checkout}</span>
              </div>
              <div className="flex items-center gap-4">
                <span className="w-20 text-right font-mono-data text-mono-data text-on-surface-variant">Purchased</span>
                <div className="flex-1 h-6 bg-surface-container-highest rounded">
                  <div className="h-full bg-gradient-to-r from-rose-400 to-orange-500 rounded" style={{ width: `${(purchased / funnelMax) * 100}%` }}></div>
                </div>
                <span className="w-12 font-mono-data text-mono-data">{purchased}</span>
              </div>
            </div>
          </div>
          
          <div className="glass-card rounded-xl p-[20px] h-64 flex flex-col">
            <h3 className="font-label-caps text-label-caps text-on-surface-variant mb-4">Dwell Time Trend</h3>
            <div className="flex-1 w-full rounded relative border-b border-secondary/30">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={conversionLine} margin={{ top: 0, right: 0, left: -20, bottom: 0 }}>
                  <defs>
                    <linearGradient id="colorDwell" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#4cd7f6" stopOpacity={0.3}/>
                      <stop offset="95%" stopColor="#4cd7f6" stopOpacity={0}/>
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="rgba(255,255,255,0.05)" />
                  <XAxis dataKey="name" tickLine={false} axisLine={false} tick={{fill: '#bbcabf', fontSize: 12}} />
                  <YAxis tickLine={false} axisLine={false} tick={{fill: '#bbcabf', fontSize: 12}} />
                  <Tooltip 
                    contentStyle={{ backgroundColor: '#1e1f26', borderColor: '#33343b', borderRadius: '8px' }}
                    itemStyle={{ color: '#e2e2eb' }}
                  />
                  <Area type="monotone" dataKey="dwell" stroke="#4cd7f6" strokeWidth={3} fillOpacity={1} fill="url(#colorDwell)" />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>

        {/* Bottom Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-gutter animate-fade-in-up opacity-0 delay-300" style={{animationDelay: "300ms", opacity: 1}}>
          <div className="space-y-gutter">
            <div className="glass-card rounded-xl p-[20px]">
              <h3 className="font-label-caps text-label-caps text-on-surface-variant mb-4">Zone Heatmap</h3>
              <div className="space-y-4">
                {heatmap.zones.map((zone, index) => (
                   <div key={zone.zone_id}>
                     <div className="flex justify-between font-mono-data text-mono-data text-on-surface-variant mb-1">
                       <span>{zone.name}</span>
                       <span>{formatSeconds(zone.avg_dwell_seconds)}</span>
                     </div>
                     <div className="h-2 w-full bg-surface-container-high rounded-full overflow-hidden">
                       <div className={`h-full ${heatmapColors[index % heatmapColors.length]} rounded-full`} style={{ width: `${Math.min(100, zone.visits * 5)}%` }}></div>
                     </div>
                   </div>
                ))}
              </div>
            </div>

            <div className="glass-card rounded-xl p-[20px]">
              <h3 className="font-label-caps text-label-caps text-on-surface-variant mb-4">Anomalies</h3>
              <div className="space-y-2">
                {anomalies.map((anomaly) => (
                  <div key={anomaly.id} className="flex justify-between items-center p-3 rounded bg-white/5 border border-white/5">
                    <span className="font-body-sm text-body-sm">{anomaly.type.replaceAll("_", " ")}</span>
                    <span className={`px-2 py-1 rounded text-[10px] uppercase font-bold border ${
                      anomaly.severity === "high" ? "bg-red-500/20 text-red-400 border-red-500/30" : 
                      anomaly.severity === "medium" ? "bg-orange-500/20 text-orange-400 border-orange-500/30" : 
                      "bg-yellow-500/20 text-yellow-400 border-yellow-500/30"
                    }`}>
                      {anomaly.severity}
                    </span>
                  </div>
                ))}
                {anomalies.length === 0 && (
                  <div className="text-sm text-on-surface-variant">No anomalies detected</div>
                )}
              </div>
            </div>
          </div>

          <div className="space-y-gutter">
            <div className="glass-card rounded-xl p-[20px] h-full flex flex-col">
              <h3 className="font-label-caps text-label-caps text-on-surface-variant mb-4">Recent Sessions</h3>
              <div className="flex-1 overflow-x-auto">
                <table className="w-full text-left font-mono-data text-mono-data whitespace-nowrap">
                  <thead className="text-on-surface-variant border-b border-white/10">
                    <tr>
                      <th className="pb-2 font-normal">Time</th>
                      <th className="pb-2 font-normal">Dwell</th>
                      <th className="pb-2 font-normal">Invoice</th>
                      <th className="pb-2 font-normal">Type</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/5">
                    {sessions.map((session, index) => (
                      <tr key={session.id} className="hover:bg-white/5 transition-colors group cursor-pointer">
                        <td className={`py-3 text-on-surface border-l-2 border-transparent group-hover:border-${index % 2 === 0 ? 'primary' : 'secondary'} pl-2`}>
                          {timeOnly(session.started_at)}
                        </td>
                        <td className={`py-3 ${session.matched_invoice ? 'text-secondary' : ''}`}>
                          {formatSeconds(session.dwell_seconds)}
                        </td>
                        <td className="py-3">{session.matched_invoice || "-"}</td>
                        <td className="py-3">
                          <span className={`material-symbols-outlined text-sm ${session.is_staff ? 'text-orange-400' : session.matched_invoice ? 'text-secondary' : 'text-on-surface-variant'}`}>
                            {session.is_staff ? 'badge' : session.matched_invoice ? 'shopping_cart' : 'person'}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </div>
      </main>

      {/* Bottom Navigation (Mobile) */}
      <nav className="md:hidden fixed bottom-0 w-full bg-surface-container-lowest/90 backdrop-blur-md border-t border-white/10 flex justify-around py-3 pb-safe z-50">
        <a className="flex flex-col items-center gap-1 text-primary" href="#">
          <span className="material-symbols-outlined">dashboard</span>
          <span className="text-[10px] font-medium">Overview</span>
        </a>
        <a className="flex flex-col items-center gap-1 text-on-surface-variant" href="#">
          <span className="material-symbols-outlined">inventory_2</span>
          <span className="text-[10px] font-medium">Inventory</span>
        </a>
        <a className="flex flex-col items-center gap-1 text-on-surface-variant" href="#">
          <span className="material-symbols-outlined">group</span>
          <span className="text-[10px] font-medium">Traffic</span>
        </a>
      </nav>
    </div>
  );
}
