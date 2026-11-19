import React, { useState } from "react";
import {
  ChevronRight,
  HardDrive,
  History,
  Plus,
  Search,
  ShieldCheck,
} from "lucide-react";
import { score, relativeDate } from "./client.js";
import { Badge } from "./components.jsx";

export function JobTable({ jobs, onOpen }) {
  return (
    <div className="job-table">
      <div className="job-table-head">
        <span>PLAYER / REPLAY</span>
        <span>MAP</span>
        <span>REVIEW SCORE</span>
        <span>RESULT</span>
        <span />
      </div>
      {jobs.length ? (
        jobs.map((job) => (
          <button className="job-row" key={job.id} onClick={() => onOpen(job)}>
            <div className="job-person">
              <span className="avatar">
                {(job.player || "?").slice(0, 2).toUpperCase()}
              </span>
              <span>
                <strong>{job.player || job.steamid}</strong>
                <small title={job.replay_name}>{job.replay_name}</small>
              </span>
            </div>
            <span className="job-map">{job.map || "CS2"}</span>
            <span className="score-cell">
              {score(job.prediction)}
              <small>/100</small>
            </span>
            <div>
              <Badge prediction={job.prediction} status={job.status} />
              <small className="job-time">
                {job.origin === "saved" ? "Saved report" : relativeDate(job.created)}
              </small>
            </div>
            <ChevronRight size={15} />
          </button>
        ))
      ) : (
        <div className="empty-history">
          <History size={19} />
          <span>Your completed and queued analyses will appear here.</span>
        </div>
      )}
    </div>
  );
}

export function HistoryPage({ jobs, onOpen, onNew }) {
  const [query, setQuery] = useState(""),
    [filter, setFilter] = useState("all");
  const filtered = jobs.filter(
    (j) =>
      `${j.player} ${j.replay_name} ${j.map}`
        .toLowerCase()
        .includes(query.toLowerCase()) &&
      (filter === "all" ||
        (filter === "review" && j.prediction?.flagged) ||
        (filter === "local" && j.origin === "local")),
  );
  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">YOUR LOCAL RECORD</div>
          <h1>
            Analysis history<span className="title-period">.</span>
          </h1>
          <p>Revisit the evidence. Every run keeps its own report.</p>
        </div>
        <button className="button primary" onClick={onNew}>
          <Plus size={16} /> New review
        </button>
      </div>
      <section className="panel history-panel">
        <div className="history-controls">
          <div className="search-box">
            <Search size={15} />
            <input
              placeholder="Search players, maps or files…"
              aria-label="Search history"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </div>
          <div className="segmented">
            {[
              ["all", "All analyses"],
              ["review", "Review flags"],
              ["local", "New runs"],
            ].map(([key, label]) => (
              <button
                key={key}
                className={filter === key ? "active" : ""}
                onClick={() => setFilter(key)}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
        <JobTable jobs={filtered} onOpen={onOpen} />
      </section>
    </>
  );
}

export function Settings({ boot, count }) {
  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">WORKSPACE DETAILS</div>
          <h1>
            Settings<span className="title-period">.</span>
          </h1>
          <p>Your analysis engine and local storage.</p>
        </div>
      </div>
      <div className="settings-grid">
        <section className="panel settings-card">
          <div className="panel-heading">
            <h2>
              <ShieldCheck size={17} /> Analysis engine
            </h2>
            <span className={`badge ${boot.model.ready ? "clear" : "review"}`}>
              {boot.model.ready ? "Verified" : "Needs attention"}
            </span>
          </div>
          <dl>
            <div>
              <dt>Detector</dt>
              <dd>AimGuard v{boot.model.version || "0.6"}</dd>
            </div>
            <div>
              <dt>Review threshold</dt>
              <dd>{(boot.model.threshold || 0.75) * 100} / 100</dd>
            </div>
            <div>
              <dt>Configured tick rate</dt>
              <dd>{boot.model.tickrate || 64} Hz</dd>
            </div>
            <div>
              <dt>Model updates</dt>
              <dd>Frozen</dd>
            </div>
          </dl>
          <p className="settings-note">
            The interface uses the existing detector in its original environment. Adding
            the interface does not retrain or change the model.
          </p>
          {boot.model.error && <pre className="error-details">{boot.model.error}</pre>}
          <details className="technical">
            <summary>Model identity</summary>
            <code>{boot.model.model_sha256 || "Unavailable"}</code>
            <p>Python {boot.model.python || "unavailable"}</p>
          </details>
        </section>
        <section className="panel settings-card">
          <div className="panel-heading">
            <h2>
              <HardDrive size={17} /> Local storage
            </h2>
          </div>
          <dl>
            <div>
              <dt>Replay files indexed</dt>
              <dd>{count}</dd>
            </div>
            <div>
              <dt>Maximum imported file</dt>
              <dd>2 GiB</dd>
            </div>
            <div>
              <dt>Processing</dt>
              <dd>On this computer</dd>
            </div>
          </dl>
          <div className="path-label">ANALYSES & IMPORTED FILES</div>
          <code className="storage-path">{boot.storage}</code>
          <p className="settings-note">
            Imported files are copied here. Using a file’s local path reads it directly.
            Results persist when you close the app.
          </p>
          <div className="local-note">
            <HardDrive size={16} />
            <span>Replay data is not sent to an external service.</span>
          </div>
        </section>
      </div>
    </>
  );
}
