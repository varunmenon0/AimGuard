import React, { useEffect, useState } from "react";
import {
  Activity,
  ArrowDownToLine,
  ArrowLeft,
  ArrowUpRight,
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Clock3,
  Crosshair,
  File,
  Info,
  MapPin,
  TriangleAlert,
  X,
} from "lucide-react";
import { api, score, statusMeta, relativeDate, weaponName } from "./client.js";
import { Spinner, Badge } from "./components.jsx";
import Trajectory from "./Trajectory.jsx";

export default function Review({
  job,
  onBack,
  onCancel,
  backLabel = "Replay workspace",
}) {
  const [evidence, setEvidence] = useState(null),
    [windowId, setWindowId] = useState(null),
    [curve, setCurve] = useState(null),
    [tab, setTab] = useState("angles"),
    [error, setError] = useState(""),
    [warnings, setWarnings] = useState(false);
  const [loadingCurve, setLoadingCurve] = useState(false);
  useEffect(() => {
    setEvidence(null);
    setCurve(null);
    setWindowId(null);
    setError("");
    if (job.status !== "completed") return;
    const controller = new AbortController();
    api(`/api/jobs/${job.id}/evidence`, { signal: controller.signal })
      .then((data) => {
        setEvidence(data);
        setWindowId(data.windows[0]?.id ?? null);
      })
      .catch((e) => {
        if (e.name !== "AbortError") setError(e.message);
      });
    return () => controller.abort();
  }, [job.id, job.status]);
  useEffect(() => {
    if (windowId == null || job.status !== "completed") return;
    const controller = new AbortController();
    setLoadingCurve(true);
    api(`/api/jobs/${job.id}/windows/${windowId}`, {
      signal: controller.signal,
    })
      .then((data) => {
        setCurve(data);
        setLoadingCurve(false);
      })
      .catch((e) => {
        if (e.name !== "AbortError") {
          setError(e.message);
          setLoadingCurve(false);
        }
      });
    return () => controller.abort();
  }, [job.id, windowId, job.status]);
  const p = job.prediction,
    [decision, kind] = statusMeta(p);
  const windows = evidence?.windows || [],
    currentIndex = windows.findIndex((w) => w.id === windowId),
    window = windows[currentIndex];
  if (["queued", "running", "failed", "cancelled", "interrupted"].includes(job.status))
    return (
      <>
        <div className="review-back">
          <button className="text-button" onClick={onBack}>
            <ArrowLeft size={15} /> {backLabel}
          </button>
        </div>
        <div className="page-heading">
          <div>
            <div className="eyebrow">PLAYER REVIEW</div>
            <h1>{job.player}</h1>
            <p>{job.replay_name}</p>
          </div>
          <Badge status={job.status} />
        </div>
        <section className="panel running-panel">
          {["queued", "running"].includes(job.status) ? (
            <>
              <div className="analysis-orbit">
                <Crosshair size={38} strokeWidth={1} />
                <span />
              </div>
              <h2>
                {job.status === "queued"
                  ? "Your review is queued."
                  : "Following the motion."}
              </h2>
              <p>{job.message}</p>
              <div className="analysis-steps">
                {[
                  "Read replay",
                  "Build windows",
                  "Track opponents",
                  "Score evidence",
                ].map((label, i) => (
                  <div
                    key={label}
                    className={
                      (job.stage ?? -1) > i
                        ? "done"
                        : job.status === "running" && (job.stage ?? 0) === i
                          ? "current"
                          : ""
                    }
                  >
                    <span>
                      {(job.stage ?? -1) > i ? (
                        <Check size={13} />
                      ) : job.status === "running" && (job.stage ?? 0) === i ? (
                        <Spinner />
                      ) : (
                        i + 1
                      )}
                    </span>
                    {label}
                  </div>
                ))}
              </div>
              <small>
                Processing stays local. Duration depends on replay size and match
                activity.
              </small>
              <button className="button secondary" onClick={onCancel}>
                <X size={14} /> Cancel analysis
              </button>
            </>
          ) : (
            <>
              <TriangleAlert size={30} className="amber" />
              <h2>
                {job.status === "cancelled"
                  ? "Analysis cancelled."
                  : "This review wasn’t completed."}
              </h2>
              <p>{job.message}</p>
              {job.detail && (
                <details className="technical">
                  <summary>Show details</summary>
                  <pre>{job.detail}</pre>
                </details>
              )}
              <button className="button primary" onClick={onBack}>
                <ArrowLeft size={15} /> Back to workspace
              </button>
            </>
          )}
        </section>
      </>
    );
  return (
    <>
      <div className="review-back">
        <button className="text-button" onClick={onBack}>
          <ArrowLeft size={15} /> {backLabel}
        </button>
        <span>
          {job.origin === "saved" ? "SAVED ANALYSIS" : "COMPLETED LOCAL ANALYSIS"}
        </span>
      </div>
      <div className="page-heading result-heading">
        <div>
          <div className="player-heading">
            <span className="avatar large">{job.player?.slice(0, 2).toUpperCase()}</span>
            <div>
              <h1>{job.player}</h1>
              <p className="mono">{job.steamid}</p>
            </div>
          </div>
        </div>
        <div className="heading-actions">
          <span className="map-label">
            <MapPin size={14} />
            {job.map || "CS2"}
          </span>
          <a className="button secondary" href={`/exports/${job.id}`}>
            <ArrowDownToLine size={15} /> Export evidence
          </a>
        </div>
      </div>
      <section className={`decision-panel ${kind}`}>
        <div className="decision-icon">
          {kind === "review" ? (
            <Crosshair size={25} strokeWidth={1.4} />
          ) : kind === "clear" ? (
            <Check size={25} strokeWidth={1.4} />
          ) : (
            <Info size={25} />
          )}
        </div>
        <div className="decision-copy">
          <div className="eyebrow">ANALYSIS RESULT</div>
          <h2>{decision}</h2>
          <p>
            {kind === "review"
              ? "The recorded patterns warrant a closer look at the evidence."
              : kind === "clear"
                ? "The review score is below the frozen model’s flag threshold."
                : "Not enough usable combat data to compute a review score."}
          </p>
        </div>
        <div className="decision-score">
          <span>REVIEW SCORE</span>
          <strong>
            {score(p)}
            <small>/100</small>
          </strong>
          <span>Flag threshold {(p?.threshold || 0.75) * 100}</span>
        </div>
      </section>
      <div className="result-meta">
        <div>
          <Activity size={16} />
          <span>
            <small>LIVE WINDOWS</small>
            <strong>{p?.windows ?? "—"}</strong>
          </span>
        </div>
        <div>
          <Crosshair size={16} />
          <span>
            <small>TRACKING SUPPORT</small>
            <strong>
              {p?.coverage?.eligible_windows ?? "—"}
              <em> / {p?.windows ?? "—"} windows</em>
            </strong>
          </span>
        </div>
        <div>
          <Clock3 size={16} />
          <span>
            <small>ANALYSIS TICK RATE</small>
            <strong>
              {evidence?.tickrate || 64}
              <em> Hz</em>
            </strong>
          </span>
        </div>
        <button
          className={p?.round_event_warnings?.length ? "has-warnings" : ""}
          onClick={() => setWarnings(!warnings)}
        >
          <TriangleAlert size={16} />
          <span>
            <small>DATA QUALITY</small>
            <strong>
              {p?.round_event_warnings?.length || 0}
              <em> boundary warnings</em>
            </strong>
          </span>
          <ChevronDown size={13} />
        </button>
      </div>
      {warnings && (
        <div className="warning-detail">
          <Info size={16} />
          <div>
            <strong>Round-boundary observations</strong>
            <p>
              The detector used eligible live-play samples. These event-boundary warnings
              are retained for review.
            </p>
            <ul>
              {p?.round_event_warnings?.map((w, i) => (
                <li key={i}>
                  {w.kind.replaceAll("_", " ")} <span>tick {w.tick}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}
      <div className="result-grid">
        <section className="panel curve-panel">
          <div className="panel-heading">
            <h2>Aim trajectories</h2>
            <span className="subtle-label">RECORDED TELEMETRY</span>
          </div>
          <div className="chart-tabs" role="tablist" aria-label="Trajectory measurements">
            {[
              ["angles", "View angles"],
              ["speed", "Angular speed"],
              ["error", "Alignment"],
              ["tracking", "Tracking"],
            ].map(([id, label]) => (
              <button
                role="tab"
                aria-selected={tab === id}
                key={id}
                className={tab === id ? "active" : ""}
                onClick={() => setTab(id)}
              >
                {label}
              </button>
            ))}
          </div>
          {curve ? (
            <div className={loadingCurve ? "chart-loading" : ""}>
              <Trajectory curve={curve} tab={tab} />
            </div>
          ) : (
            <div className="chart-placeholder">
              {error ? (
                <>
                  <TriangleAlert size={22} />
                  <p>{error}</p>
                </>
              ) : windows.length || !evidence ? (
                <>
                  <Spinner />
                  <p>Loading recorded trajectories…</p>
                </>
              ) : (
                <>
                  <Activity size={25} />
                  <p>No eligible combat windows to display.</p>
                </>
              )}
            </div>
          )}
          {windows.length > 0 && (
            <div className="window-controls">
              <div className="window-select">
                <span>COMBAT WINDOW</span>
                <select
                  aria-label="Select combat window"
                  value={windowId ?? ""}
                  onChange={(e) => setWindowId(Number(e.target.value))}
                >
                  {windows.map((w, i) => (
                    <option key={w.id} value={w.id}>
                      {String(i + 1).padStart(2, "0")} · Round {w.round} ·{" "}
                      {weaponName(w.weapon)}
                    </option>
                  ))}
                </select>
                <ChevronDown size={13} />
              </div>
              <div className="window-numbers">
                <button
                  className="icon-button"
                  aria-label="Previous combat window"
                  disabled={currentIndex <= 0}
                  onClick={() => setWindowId(windows[currentIndex - 1].id)}
                >
                  <ChevronLeft size={17} />
                </button>
                <span>
                  {currentIndex + 1}
                  <i>/ {windows.length}</i>
                </span>
                <button
                  className="icon-button"
                  aria-label="Next combat window"
                  disabled={currentIndex >= windows.length - 1}
                  onClick={() => setWindowId(windows[currentIndex + 1].id)}
                >
                  <ChevronRight size={17} />
                </button>
              </div>
            </div>
          )}
          {window && (
            <div className="window-facts">
              <span>{weaponName(window.weapon)}</span>
              <span>
                {window.shots} {window.shots === 1 ? "shot" : "shots"}
              </span>
              <span>{window.damage} damage events</span>
              <span>{window.duration.toFixed(2)}s window</span>
            </div>
          )}
        </section>
        <aside className="panel signals-panel">
          <div className="panel-heading">
            <h2>Score drivers</h2>
            <Info size={14} className="muted" />
          </div>
          <p className="signals-description">
            How each measured feature contributes to this player’s review score.
          </p>
          <div className="signal-list">
            {[
              ["p95_speed", "Angular speed"],
              ["mean_accel", "Acceleration"],
              ["median_pre_shot_absolute_error_degrees", "Aim alignment"],
              ["median_pre_shot_absolute_relative_rate_dps", "Relative motion"],
            ].map(([key, label]) => {
              const value = p?.contributions?.[key];
              const width =
                value == null
                  ? 0
                  : Math.min(
                      (Math.abs(value) /
                        Math.max(1, ...Object.values(p.contributions).map(Math.abs))) *
                        100,
                      100,
                    );
              return (
                <div className="signal" key={key}>
                  <div>
                    <span>{label}</span>
                    <code className={value > 0 ? "positive" : "negative"}>
                      {value == null
                        ? "—"
                        : `${value >= 0 ? "+" : ""}${value.toFixed(2)}`}
                    </code>
                  </div>
                  <div className="signal-track">
                    <span
                      className={value > 0 ? "positive-bar" : "negative-bar"}
                      style={{ width: `${width}%` }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
          <div className="signal-legend">
            <span>
              <i className="positive-key" /> Raises score
            </span>
            <span>
              <i className="negative-key" /> Lowers score
            </span>
          </div>
          <p className="signal-note">
            Contributions are signed model values. The review score is not a cheating
            probability.
          </p>
          <a
            className="evidence-link"
            href={`/reports/${job.id}/analysis/review.html`}
            target="_blank"
            rel="noreferrer"
          >
            Open full evidence report <ArrowUpRight size={15} />
          </a>
        </aside>
      </div>
      <div className="review-source">
        <File size={13} />
        <span title={job.replay_name}>{job.replay_name}</span>
        <span>
          Frozen model v{p?.feature_version || "0.6"}
          <i /> {relativeDate(job.finished || job.created)}
        </span>
      </div>
    </>
  );
}
