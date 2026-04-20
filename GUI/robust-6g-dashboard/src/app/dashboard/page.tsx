"use client";

import { useSession } from "next-auth/react";
import {
  Users,
  Shield,
  Activity,
  AlertTriangle,
  Monitor,
  UserPlus,
  ClipboardList,
  Server,
  ArrowUpRight,
  ArrowDownRight,
  Clock,
  CheckCircle,
  XCircle,
  ChevronRight,
  Settings,
  ToggleLeft,
  ToggleRight,
  Eye,
  Wrench,
  BarChart3,
  Network,
  Lock,
  FileSearch,
  Layers,
  Cpu,
  Plug,
  Power,
} from "lucide-react";

// ─── KPI Card ───────────────────────────────────────────────
function KpiCard({
  title,
  value,
  change,
  changeType,
  icon: Icon,
  color,
}: {
  title: string;
  value: string;
  change: string;
  changeType: "up" | "down" | "neutral";
  icon: React.ElementType;
  color: string;
}) {
  const colorMap: Record<string, string> = {
    blue: "bg-blue-500/10 text-blue-400",
    green: "bg-green-500/10 text-green-400",
    purple: "bg-purple-500/10 text-purple-400",
    amber: "bg-amber-500/10 text-amber-400",
    cyan: "bg-cyan-500/10 text-cyan-400",
    red: "bg-red-500/10 text-red-400",
  };

  return (
    <div className="rounded-xl border border-gray-800 bg-gray-900/50 p-5 transition-all hover:border-gray-700">
      <div className="flex items-center justify-between">
        <p className="text-sm text-gray-400">{title}</p>
        <div className={`rounded-lg p-2 ${colorMap[color]}`}>
          <Icon className="h-5 w-5" />
        </div>
      </div>
      <p className="mt-3 text-3xl font-bold text-white">{value}</p>
      <div className="mt-2 flex items-center gap-1 text-xs">
        {changeType === "up" && (
          <ArrowUpRight className="h-3 w-3 text-green-400" />
        )}
        {changeType === "down" && (
          <ArrowDownRight className="h-3 w-3 text-red-400" />
        )}
        <span
          className={
            changeType === "up"
              ? "text-green-400"
              : changeType === "down"
                ? "text-red-400"
                : "text-gray-500"
          }
        >
          {change}
        </span>
        <span className="text-gray-600">vs last week</span>
      </div>
    </div>
  );
}

// ─── Status Badge ───────────────────────────────────────────
function StatusBadge({
  status,
}: {
  status: "online" | "degraded" | "offline";
}) {
  const config = {
    online: {
      label: "Online",
      className: "bg-green-500/10 text-green-400",
      icon: CheckCircle,
    },
    degraded: {
      label: "Degraded",
      className: "bg-amber-500/10 text-amber-400",
      icon: AlertTriangle,
    },
    offline: {
      label: "Offline",
      className: "bg-red-500/10 text-red-400",
      icon: XCircle,
    },
  };
  const { label, className, icon: Icon } = config[status];
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium ${className}`}
    >
      <Icon className="h-3 w-3" />
      {label}
    </span>
  );
}

// ─── Toggle Switch (for Admin tool activation) ──────────────
function ToolToggle({
  name,
  description,
  enabled,
  icon: Icon,
}: {
  name: string;
  description: string;
  enabled: boolean;
  icon: React.ElementType;
}) {
  return (
    <div className="flex items-center justify-between rounded-lg border border-gray-800 bg-gray-950/50 p-4 transition-all hover:border-gray-700">
      <div className="flex items-center gap-3">
        <div className="rounded-lg bg-purple-500/10 p-2 text-purple-400">
          <Icon className="h-5 w-5" />
        </div>
        <div>
          <p className="text-sm font-medium text-white">{name}</p>
          <p className="text-xs text-gray-500">{description}</p>
        </div>
      </div>
      <button
        className={`flex items-center gap-1 rounded-full px-3 py-1.5 text-xs font-medium transition-all ${
          enabled
            ? "bg-green-500/10 text-green-400 hover:bg-green-500/20"
            : "bg-gray-800 text-gray-500 hover:bg-gray-700"
        }`}
      >
        {enabled ? (
          <>
            <ToggleRight className="h-4 w-4" /> Active
          </>
        ) : (
          <>
            <ToggleLeft className="h-4 w-4" /> Inactive
          </>
        )}
      </button>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
// ADMIN DASHBOARD
// ═══════════════════════════════════════════════════════════════
function AdminDashboard() {
  return (
    <div className="space-y-6">
      {/* Welcome banner */}
      <div className="rounded-xl border border-purple-500/20 bg-gradient-to-r from-purple-900/20 via-blue-900/20 to-cyan-900/20 p-6">
        <h1 className="text-2xl font-bold text-white">
          Platform Administration
        </h1>
        <p className="mt-1 text-sm text-gray-400">
          Configure tools, manage users, and monitor system health across the
          ROBUST-6G Programmable Monitoring Platform.
        </p>
      </div>

      {/* KPI Row */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <KpiCard
          title="Registered Users"
          value="24"
          change="+3"
          changeType="up"
          icon={Users}
          color="blue"
        />
        <KpiCard
          title="Active Tools"
          value="6 / 9"
          change="+1"
          changeType="up"
          icon={Wrench}
          color="purple"
        />
        <KpiCard
          title="Active Visualizations"
          value="4"
          change="+2"
          changeType="up"
          icon={BarChart3}
          color="cyan"
        />
        <KpiCard
          title="System Alerts"
          value="2"
          change="-1"
          changeType="down"
          icon={AlertTriangle}
          color="amber"
        />
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* ─── Tool Activation Panel ─────────────────────────── */}
        <div className="lg:col-span-2 rounded-xl border border-gray-800 bg-gray-900/50 p-6">
          <div className="mb-5 flex items-center justify-between">
            <h3 className="flex items-center gap-2 text-lg font-semibold text-white">
              <Settings className="h-5 w-5 text-purple-400" />
              Platform Tools &amp; Functions
            </h3>
            <span className="rounded-full bg-purple-500/10 px-3 py-1 text-xs font-medium text-purple-400">
              6 of 9 active
            </span>
          </div>
          <div className="space-y-3">
            <ToolToggle
              name="Network Traffic Analyzer"
              description="Deep packet inspection and flow analysis"
              enabled={true}
              icon={Network}
            />
            <ToolToggle
              name="Intrusion Detection System"
              description="Signature & anomaly-based detection engine"
              enabled={true}
              icon={Shield}
            />
            <ToolToggle
              name="Vulnerability Scanner"
              description="Automated CVE scanning across infrastructure"
              enabled={true}
              icon={FileSearch}
            />
            <ToolToggle
              name="DDoS Mitigation Module"
              description="Volumetric and application-layer DDoS protection"
              enabled={false}
              icon={Lock}
            />
            <ToolToggle
              name="Log Aggregation Pipeline"
              description="Centralized log collection and indexing"
              enabled={true}
              icon={Layers}
            />
            <ToolToggle
              name="AI Anomaly Engine"
              description="ML-based behavioral anomaly detection"
              enabled={false}
              icon={Cpu}
            />
          </div>
        </div>

        {/* ─── System Health ─────────────────────────────────── */}
        <div className="rounded-xl border border-gray-800 bg-gray-900/50 p-6">
          <h3 className="mb-4 flex items-center gap-2 text-lg font-semibold text-white">
            <Server className="h-5 w-5 text-cyan-400" />
            System Health
          </h3>
          <div className="space-y-3">
            {[
              { name: "Auth Service", status: "online" as const },
              { name: "PostgreSQL", status: "online" as const },
              { name: "Monitoring Pipeline", status: "online" as const },
              { name: "External API Proxy", status: "degraded" as const },
              { name: "Alert Engine", status: "online" as const },
              { name: "Visualization Server", status: "online" as const },
            ].map((s, i) => (
              <div
                key={i}
                className="flex items-center justify-between rounded-lg border border-gray-800 bg-gray-950/50 p-3"
              >
                <p className="text-sm text-gray-300">{s.name}</p>
                <StatusBadge status={s.status} />
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* ─── Visualization Dashboards ──────────────────────── */}
        <div className="rounded-xl border border-gray-800 bg-gray-900/50 p-6">
          <div className="mb-4 flex items-center justify-between">
            <h3 className="flex items-center gap-2 text-lg font-semibold text-white">
              <Eye className="h-5 w-5 text-cyan-400" />
              Visualization Dashboards
            </h3>
            <button className="flex items-center gap-1 rounded-lg bg-cyan-500/10 px-3 py-1.5 text-xs font-medium text-cyan-400 hover:bg-cyan-500/20 transition-colors">
              <Plug className="h-3 w-3" /> Add Dashboard
            </button>
          </div>
          <div className="space-y-3">
            {[
              {
                name: "Network Overview",
                type: "Grafana",
                active: true,
                viewers: 8,
              },
              {
                name: "Threat Intelligence Feed",
                type: "Custom",
                active: true,
                viewers: 5,
              },
              {
                name: "Infrastructure Metrics",
                type: "Grafana",
                active: true,
                viewers: 12,
              },
              {
                name: "Incident Timeline",
                type: "Kibana",
                active: false,
                viewers: 0,
              },
            ].map((dash, i) => (
              <div
                key={i}
                className="flex items-center justify-between rounded-lg border border-gray-800 bg-gray-950/50 p-4"
              >
                <div className="flex items-center gap-3">
                  <div
                    className={`h-2.5 w-2.5 rounded-full ${
                      dash.active ? "bg-green-400" : "bg-gray-600"
                    }`}
                  />
                  <div>
                    <p className="text-sm font-medium text-white">
                      {dash.name}
                    </p>
                    <p className="text-xs text-gray-500">
                      {dash.type} • {dash.viewers} viewer(s)
                    </p>
                  </div>
                </div>
                <button
                  className={`flex items-center gap-1 rounded-full px-3 py-1 text-xs font-medium transition-all ${
                    dash.active
                      ? "bg-green-500/10 text-green-400 hover:bg-green-500/20"
                      : "bg-gray-800 text-gray-500 hover:bg-gray-700"
                  }`}
                >
                  <Power className="h-3 w-3" />
                  {dash.active ? "Active" : "Activate"}
                </button>
              </div>
            ))}
          </div>
        </div>

        {/* ─── Recent Audit Log ──────────────────────────────── */}
        <div className="rounded-xl border border-gray-800 bg-gray-900/50 p-6">
          <div className="mb-4 flex items-center justify-between">
            <h3 className="flex items-center gap-2 text-lg font-semibold text-white">
              <ClipboardList className="h-5 w-5 text-purple-400" />
              Recent Audit Log
            </h3>
            <button className="flex items-center gap-1 text-xs text-cyan-400 hover:text-cyan-300 transition-colors">
              View all <ChevronRight className="h-3 w-3" />
            </button>
          </div>
          <div className="space-y-3">
            {[
              {
                action: "Tool activated",
                target: "Log Aggregation Pipeline",
                actor: "admin@robust-6g.eu",
                time: "5 min ago",
                type: "update",
              },
              {
                action: "User created",
                target: "analyst2@robust-6g.eu",
                actor: "admin@robust-6g.eu",
                time: "1 hour ago",
                type: "create",
              },
              {
                action: "Dashboard activated",
                target: "Network Overview",
                actor: "admin@robust-6g.eu",
                time: "3 hours ago",
                type: "update",
              },
              {
                action: "Role changed",
                target: "maria@robust-6g.org",
                actor: "admin@robust-6g.eu",
                time: "5 hours ago",
                type: "update",
              },
              {
                action: "Tool deactivated",
                target: "DDoS Mitigation",
                actor: "admin@robust-6g.eu",
                time: "1 day ago",
                type: "delete",
              },
              {
                action: "Login failed",
                target: "unknown@gmail.com",
                actor: "System",
                time: "1 day ago",
                type: "alert",
              },
            ].map((log, i) => (
              <div
                key={i}
                className="flex items-center justify-between rounded-lg border border-gray-800 bg-gray-950/50 p-3"
              >
                <div className="flex items-center gap-3">
                  <div
                    className={`h-2 w-2 rounded-full ${
                      log.type === "create"
                        ? "bg-green-400"
                        : log.type === "update"
                          ? "bg-blue-400"
                          : log.type === "delete"
                            ? "bg-red-400"
                            : "bg-amber-400"
                    }`}
                  />
                  <div>
                    <p className="text-sm text-white">{log.action}</p>
                    <p className="text-xs text-gray-500">{log.target}</p>
                  </div>
                </div>
                <div className="text-right">
                  <p className="text-xs text-gray-500">{log.actor}</p>
                  <p className="text-xs text-gray-600">{log.time}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* ─── Quick Actions ───────────────────────────────────── */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {[
          {
            label: "Create User",
            icon: UserPlus,
            color: "blue",
            href: "/dashboard/users",
          },
          {
            label: "Manage Tools",
            icon: Wrench,
            color: "purple",
            href: "/dashboard/tools",
          },
          {
            label: "Visualization Config",
            icon: Eye,
            color: "cyan",
            href: "/dashboard/visualizations",
          },
          {
            label: "Platform Settings",
            icon: Settings,
            color: "amber",
            href: "/dashboard/settings",
          },
        ].map((action, i) => (
          <a
            key={i}
            href={action.href}
            className="group flex items-center gap-3 rounded-xl border border-gray-800 bg-gray-900/50 p-4 transition-all hover:border-gray-700 hover:bg-gray-900"
          >
            <div
              className={`rounded-lg p-2 ${
                action.color === "blue"
                  ? "bg-blue-500/10 text-blue-400"
                  : action.color === "purple"
                    ? "bg-purple-500/10 text-purple-400"
                    : action.color === "cyan"
                      ? "bg-cyan-500/10 text-cyan-400"
                      : "bg-amber-500/10 text-amber-400"
              }`}
            >
              <action.icon className="h-5 w-5" />
            </div>
            <span className="text-sm font-medium text-gray-300 group-hover:text-white transition-colors">
              {action.label}
            </span>
            <ChevronRight className="ml-auto h-4 w-4 text-gray-600 group-hover:text-gray-400 transition-colors" />
          </a>
        ))}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
// ANALYST DASHBOARD
// ═══════════════════════════════════════════════════════════════
function AnalystDashboard() {
  return (
    <div className="space-y-6">
      {/* Welcome banner */}
      <div className="rounded-xl border border-cyan-500/20 bg-gradient-to-r from-cyan-900/20 via-blue-900/20 to-purple-900/20 p-6">
        <h1 className="text-2xl font-bold text-white">Security Monitoring</h1>
        <p className="mt-1 text-sm text-gray-400">
          Real-time threat detection, active alerts, and monitoring dashboards
          assigned to your profile.
        </p>
      </div>

      {/* KPI Row */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <KpiCard
          title="Active Alerts"
          value="7"
          change="+3"
          changeType="up"
          icon={AlertTriangle}
          color="amber"
        />
        <KpiCard
          title="Monitored Services"
          value="5"
          change="+1"
          changeType="up"
          icon={Monitor}
          color="cyan"
        />
        <KpiCard
          title="Resolved Today"
          value="12"
          change="+4"
          changeType="up"
          icon={CheckCircle}
          color="green"
        />
        <KpiCard
          title="Avg Response Time"
          value="2.4s"
          change="-0.3s"
          changeType="down"
          icon={Clock}
          color="purple"
        />
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* ─── Active Alerts ─────────────────────────────────── */}
        <div className="lg:col-span-2 rounded-xl border border-gray-800 bg-gray-900/50 p-6">
          <div className="mb-4 flex items-center justify-between">
            <h3 className="flex items-center gap-2 text-lg font-semibold text-white">
              <AlertTriangle className="h-5 w-5 text-amber-400" />
              Active Alerts
            </h3>
            <button className="flex items-center gap-1 text-xs text-cyan-400 hover:text-cyan-300 transition-colors">
              View all <ChevronRight className="h-3 w-3" />
            </button>
          </div>
          <div className="space-y-3">
            {[
              {
                severity: "critical",
                title: "Unusual traffic spike detected on Node 7",
                source: "Network Traffic Analyzer",
                time: "5 min ago",
              },
              {
                severity: "high",
                title: "Brute-force attempt from 192.168.1.45",
                source: "Intrusion Detection System",
                time: "12 min ago",
              },
              {
                severity: "medium",
                title: "Latency increase on API Gateway",
                source: "Infrastructure Metrics",
                time: "30 min ago",
              },
              {
                severity: "low",
                title: "TLS certificate expiring in 14 days",
                source: "Vulnerability Scanner",
                time: "1 hour ago",
              },
              {
                severity: "medium",
                title: "Disk usage above 80% on DB node",
                source: "Log Aggregation Pipeline",
                time: "2 hours ago",
              },
              {
                severity: "critical",
                title: "Unauthorized access attempt on admin endpoint",
                source: "Intrusion Detection System",
                time: "3 hours ago",
              },
            ].map((alert, i) => (
              <div
                key={i}
                className="flex items-center justify-between rounded-lg border border-gray-800 bg-gray-950/50 p-4"
              >
                <div className="flex items-center gap-3">
                  <div
                    className={`h-2.5 w-2.5 rounded-full ${
                      alert.severity === "critical"
                        ? "bg-red-500 animate-pulse"
                        : alert.severity === "high"
                          ? "bg-orange-400"
                          : alert.severity === "medium"
                            ? "bg-amber-400"
                            : "bg-blue-400"
                    }`}
                  />
                  <div>
                    <p className="text-sm text-white">{alert.title}</p>
                    <p className="text-xs text-gray-500">{alert.source}</p>
                  </div>
                </div>
                <div className="flex flex-col items-end gap-1">
                  <span
                    className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${
                      alert.severity === "critical"
                        ? "bg-red-500/10 text-red-400"
                        : alert.severity === "high"
                          ? "bg-orange-500/10 text-orange-400"
                          : alert.severity === "medium"
                            ? "bg-amber-500/10 text-amber-400"
                            : "bg-blue-500/10 text-blue-400"
                    }`}
                  >
                    {alert.severity}
                  </span>
                  <p className="text-xs text-gray-600">{alert.time}</p>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* ─── Monitored Services ────────────────────────────── */}
        <div className="rounded-xl border border-gray-800 bg-gray-900/50 p-6">
          <h3 className="mb-4 flex items-center gap-2 text-lg font-semibold text-white">
            <Activity className="h-5 w-5 text-green-400" />
            Monitored Services
          </h3>
          <div className="space-y-3">
            {[
              {
                name: "Network Traffic Analyzer",
                status: "online" as const,
                alerts: 2,
              },
              {
                name: "Intrusion Detection",
                status: "online" as const,
                alerts: 3,
              },
              {
                name: "Vulnerability Scanner",
                status: "online" as const,
                alerts: 1,
              },
              { name: "Log Aggregation", status: "online" as const, alerts: 1 },
              {
                name: "AI Anomaly Engine",
                status: "offline" as const,
                alerts: 0,
              },
            ].map((service, i) => (
              <div
                key={i}
                className="flex items-center justify-between rounded-lg border border-gray-800 bg-gray-950/50 p-3"
              >
                <div>
                  <p className="text-sm text-gray-300">{service.name}</p>
                  {service.alerts > 0 && (
                    <p className="text-xs text-amber-400">
                      {service.alerts} active alert(s)
                    </p>
                  )}
                </div>
                <StatusBadge status={service.status} />
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* ─── Active Visualization Dashboards ─────────────────── */}
      <div className="rounded-xl border border-gray-800 bg-gray-900/50 p-6">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="flex items-center gap-2 text-lg font-semibold text-white">
            <Eye className="h-5 w-5 text-cyan-400" />
            Your Active Dashboards
          </h3>
        </div>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {[
            {
              name: "Network Overview",
              type: "Grafana",
              description: "Real-time traffic, bandwidth, and flow analysis",
              color: "cyan",
            },
            {
              name: "Threat Intelligence Feed",
              type: "Custom",
              description: "Live threat indicators and IOC correlation",
              color: "red",
            },
            {
              name: "Infrastructure Metrics",
              type: "Grafana",
              description: "CPU, memory, disk, and service metrics",
              color: "green",
            },
          ].map((dash, i) => (
            <a
              key={i}
              href="#"
              className="group rounded-xl border border-gray-800 bg-gray-950/50 p-5 transition-all hover:border-gray-700 hover:bg-gray-900/80"
            >
              <div className="mb-3 flex items-center justify-between">
                <span
                  className={`rounded-full px-2.5 py-1 text-xs font-medium ${
                    dash.color === "cyan"
                      ? "bg-cyan-500/10 text-cyan-400"
                      : dash.color === "red"
                        ? "bg-red-500/10 text-red-400"
                        : "bg-green-500/10 text-green-400"
                  }`}
                >
                  {dash.type}
                </span>
                <ChevronRight className="h-4 w-4 text-gray-600 group-hover:text-gray-400 transition-colors" />
              </div>
              <h4 className="text-sm font-semibold text-white group-hover:text-cyan-300 transition-colors">
                {dash.name}
              </h4>
              <p className="mt-1 text-xs text-gray-500">{dash.description}</p>
            </a>
          ))}
        </div>
      </div>

      {/* ─── Recent Activity Timeline ────────────────────────── */}
      <div className="rounded-xl border border-gray-800 bg-gray-900/50 p-6">
        <h3 className="mb-4 flex items-center gap-2 text-lg font-semibold text-white">
          <Clock className="h-5 w-5 text-blue-400" />
          Recent Activity
        </h3>
        <div className="relative space-y-4 pl-6 before:absolute before:left-[9px] before:top-2 before:h-[calc(100%-16px)] before:w-px before:bg-gray-800">
          {[
            {
              action: "Resolved alert",
              detail: "Brute-force attempt mitigated",
              time: "10 min ago",
              color: "bg-green-400",
            },
            {
              action: "Investigated anomaly",
              detail: "Traffic spike on Node 7 — false positive",
              time: "25 min ago",
              color: "bg-blue-400",
            },
            {
              action: "Opened dashboard",
              detail: "Network Overview (Grafana)",
              time: "1 hour ago",
              color: "bg-cyan-400",
            },
            {
              action: "Escalated alert",
              detail: "Unauthorized admin endpoint access → Incident #42",
              time: "3 hours ago",
              color: "bg-amber-400",
            },
            {
              action: "Logged in",
              detail: "Session started from 10.0.1.22",
              time: "4 hours ago",
              color: "bg-purple-400",
            },
          ].map((event, i) => (
            <div key={i} className="relative flex gap-4">
              <div
                className={`absolute -left-[15px] top-1.5 h-3 w-3 rounded-full border-2 border-gray-900 ${event.color}`}
              />
              <div>
                <p className="text-sm text-white">{event.action}</p>
                <p className="text-xs text-gray-500">{event.detail}</p>
                <p className="mt-0.5 text-xs text-gray-600">{event.time}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
// MAIN DASHBOARD PAGE — renders based on role
// ═══════════════════════════════════════════════════════════════
export default function DashboardPage() {
  const { data: session } = useSession();
  const role = (session?.user as any)?.role as "ADMIN" | "ANALYST" | undefined;

  return (
    <div className="min-h-screen bg-[#0a0e27] p-6">
      {role === "ADMIN" && <AdminDashboard />}
      {role === "ANALYST" && <AnalystDashboard />}
      {!role && (
        <div className="flex items-center justify-center py-20">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-gray-700 border-t-cyan-400" />
        </div>
      )}
    </div>
  );
}
