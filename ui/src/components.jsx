import React from "react";
import { LoaderCircle, Circle, Crosshair } from "lucide-react";
import { statusMeta } from "./client.js";

export function Spinner() {
  return <LoaderCircle size={16} className="spin" />;
}

export function Badge({ prediction, status }) {
  if (status && status !== "completed")
    return (
      <span
        className={`badge ${["failed", "interrupted"].includes(status) ? "review" : "neutral"}`}
      >
        {status === "running" || status === "queued" ? <Spinner /> : <Circle size={10} />}
        {{
          running: "Analyzing",
          queued: "Queued",
          failed: "Failed",
          cancelled: "Cancelled",
          interrupted: "Interrupted",
        }[status] || status}
      </span>
    );
  const [label, kind] = statusMeta(prediction);
  return (
    <span className={`badge ${kind}`}>
      <span className="status-dot" />
      {label}
    </span>
  );
}
export function Empty({ icon: Icon = Crosshair, title, children }) {
  return (
    <div className="empty">
      <div className="empty-icon">
        <Icon size={24} strokeWidth={1.3} />
      </div>
      <h3>{title}</h3>
      <p>{children}</p>
    </div>
  );
}

export function MatchBadge({ status }) {
  const active = ["running", "queued"].includes(status);
  return (
    <span
      className={`badge ${status === "completed" ? "clear" : active ? "neutral" : "review"}`}
    >
      {active ? <Spinner /> : <span className="status-dot" />}
      {{
        queued: "Match queued",
        running: "Analyzing match",
        completed: "Match complete",
        partial: "Incomplete match",
        cancelled: "Match cancelled",
      }[status] || status}
    </span>
  );
}
