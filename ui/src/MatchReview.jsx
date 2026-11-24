import React from "react";
import { ArrowLeft, ChevronRight, Users, X } from "lucide-react";
import { Badge, MatchBadge } from "./components.jsx";
import { score } from "./client.js";

export default function MatchReview({ match, onBack, onOpen, onCancel }) {
  const c = match.counts,
    active = ["queued", "running"].includes(match.status);
  const unresolved = c.insufficient + c.failed + c.cancelled + c.interrupted;
  const terminal = c.completed + c.failed + c.cancelled + c.interrupted;
  return (
    <>
      <div className="review-back">
        <button className="text-button" onClick={onBack}>
          <ArrowLeft size={15} /> Replay workspace
        </button>
        <span>WHOLE-MATCH REVIEW</span>
      </div>
      <div className="page-heading">
        <div>
          <div className="eyebrow">EVERY PLAYER, ONE RECORDING</div>
          <h1>
            Match review<span className="title-period">.</span>
          </h1>
          <p>
            {match.replay_name} · {match.map || "CS2"}
          </p>
        </div>
        <MatchBadge status={match.status} />
      </div>
      <section className="panel match-overview">
        <div className="match-progress-heading">
          <div>
            <Users size={19} />
            <strong>
              {c.completed} of {c.total} reviews completed
            </strong>
          </div>
          {active && (
            <button className="button secondary" onClick={onCancel}>
              <X size={14} /> Cancel remaining
            </button>
          )}
        </div>
        <div className="progress-track">
          <span style={{ width: `${c.total ? (terminal / c.total) * 100 : 0}%` }} />
        </div>
        <div className="match-metrics">
          {[
            [c.flagged, "Review flags"],
            [c.not_flagged, "No review flag"],
            [unresolved, "Unresolved"],
            [c.queued + c.running, "Pending"],
          ].map(([n, label]) => (
            <div key={label}>
              <strong>{n}</strong>
              <span>{label}</span>
            </div>
          ))}
        </div>
        <p className="match-note">
          Each human player is scored separately with the frozen detector. Players run one
          at a time; large matches can take several minutes. A non-flag does not certify
          legitimate play. Incomplete and insufficient-evidence results remain unresolved.
        </p>
      </section>
      <section className="panel match-players">
        <div className="panel-heading">
          <h2>Player results</h2>
          <span className="subtle-label">OPEN A COMPLETED REVIEW FOR EVIDENCE</span>
        </div>
        {match.jobs.map((job) => (
          <div className="match-player" key={job.id}>
            <div className="job-person">
              <span className="avatar">
                {(job.player || "?").slice(0, 2).toUpperCase()}
              </span>
              <span>
                <strong>{job.player}</strong>
                <small>{job.steamid}</small>
              </span>
            </div>
            <div className="match-player-result">
              <span className="score-cell">
                {score(job.prediction)}
                <small>/100</small>
              </span>
              <Badge prediction={job.prediction} status={job.status} />
            </div>
            <button
              className="button secondary"
              disabled={["queued", "running"].includes(job.status)}
              onClick={() => onOpen(job)}
            >
              {job.status === "completed" ? "View evidence" : "View details"}{" "}
              <ChevronRight size={14} />
            </button>
          </div>
        ))}
      </section>
    </>
  );
}
