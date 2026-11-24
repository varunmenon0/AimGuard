import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowRight,
  ArrowUpRight,
  ChevronDown,
  ChevronRight,
  Crosshair,
  Database,
  File,
  FilePlus2,
  FolderOpen,
  HardDrive,
  History,
  Info,
  MapPin,
  Play,
  Plus,
  RefreshCw,
  Search,
  Settings2,
  ShieldCheck,
  SlidersHorizontal,
  TriangleAlert,
  X,
} from "lucide-react";
import { createRoot } from "react-dom/client";
import { api, bytes, mapCode, setSessionToken } from "./client.js";
import { Spinner, Empty } from "./components.jsx";
import { JobTable, HistoryPage, Settings } from "./LibraryPages.jsx";
import ImportDialog from "./ImportDialog.jsx";
import Review from "./Review.jsx";
import MatchReview from "./MatchReview.jsx";
import "./style.css";

function Brand() {
  return (
    <div className="brand">
      <svg viewBox="0 0 32 32" aria-hidden="true">
        <path d="M5 22 16 5l11 17M10 19h12M10 27h12" />
        <path d="M3 6v6M3 6h6M29 26v-6M29 26h-6" className="brand-faint" />
      </svg>
      <div>
        aimguard<span>REPLAY WORKSPACE</span>
      </div>
    </div>
  );
}
function App() {
  const [boot, setBoot] = useState(null),
    [replays, setReplays] = useState([]),
    [jobs, setJobs] = useState([]),
    [matches, setMatches] = useState([]);
  const [page, setPage] = useState("workspace"),
    [selected, setSelected] = useState(null),
    [player, setPlayer] = useState(null),
    [roster, setRoster] = useState(null);
  const [inspection, setInspection] = useState(null),
    [inspectError, setInspectError] = useState(""),
    [activeId, setActiveId] = useState(null);
  const [query, setQuery] = useState(""),
    [map, setMap] = useState("all"),
    [importing, setImporting] = useState(false),
    [toast, setToast] = useState(""),
    [connected, setConnected] = useState(true);
  const [starting, setStarting] = useState(false),
    [refreshing, setRefreshing] = useState(false);
  const searchRef = useRef(null),
    selectionSeq = useRef(0);
  const notify = useCallback((message) => {
    setToast(message);
  }, []);
  useEffect(() => {
    if (toast) {
      const timer = setTimeout(() => setToast(""), 6500);
      return () => clearTimeout(timer);
    }
  }, [toast]);
  useEffect(() => {
    fetch("/api/bootstrap")
      .then((r) => r.json())
      .then(async (data) => {
        setSessionToken(data.token);
        setBoot(data);
        const [files, history, matchHistory] = await Promise.all([
          api("/api/replays"),
          api("/api/jobs"),
          api("/api/matches"),
        ]);
        setReplays(files);
        setJobs(history);
        setMatches(matchHistory);
        const last = localStorage.getItem("aimguard:last-analysis");
        if ([...history, ...matchHistory].some((j) => j.id === last)) setActiveId(last);
      })
      .catch(() => {
        setConnected(false);
        notify(
          "AimGuard is not connected. Keep its launch window open, then reload this page.",
        );
      });
  }, []);
  useEffect(() => {
    const handler = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "o") {
        e.preventDefault();
        setImporting(true);
      }
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        searchRef.current?.focus();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);
  useEffect(() => {
    if (!boot) return;
    let alive = true;
    const timer = setInterval(async () => {
      try {
        const [history, matchHistory] = await Promise.all([
          api("/api/jobs"),
          api("/api/matches"),
        ]);
        if (alive) {
          setJobs(history);
          setMatches(matchHistory);
          setConnected(true);
        }
        if (inspection) {
          const job = await api(`/api/jobs/${inspection}`);
          if (!alive) return;
          if (job.status === "completed") {
            const meta = await api(`/api/replays/${selected}/players`);
            if (alive && meta.status === "ready") {
              setRoster(meta);
              setPlayer(meta.players?.[0]?.steamid || null);
              setInspection(null);
              setReplays(await api("/api/replays"));
            }
          } else if (["failed", "cancelled", "interrupted"].includes(job.status)) {
            setInspectError(job.detail || job.message);
            setInspection(null);
          }
        }
      } catch {
        if (alive) setConnected(false);
      }
    }, 1300);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [boot, inspection, selected]);
  const choose = async (replay) => {
    const sequence = ++selectionSeq.current;
    setSelected(replay.id);
    setActiveId(null);
    setRoster(null);
    setPlayer(null);
    setInspectError("");
    setInspection(null);
    try {
      const result = await api(`/api/replays/${replay.id}/players`);
      if (sequence !== selectionSeq.current) return;
      if (result.status === "ready") {
        setRoster(result);
        setPlayer(result.players[0]?.steamid);
      } else setInspection(result.job.id);
    } catch (e) {
      if (sequence === selectionSeq.current) setInspectError(e.message);
    }
  };
  const open = (job) => {
    setActiveId(job.id);
    setPage("workspace");
    localStorage.setItem("aimguard:last-analysis", job.id);
  };
  const start = async () => {
    setStarting(true);
    try {
      const job = await api("/api/analyses", {
        method: "POST",
        body: JSON.stringify({ replay_id: selected, steamid: player }),
      });
      setJobs((previous) => [job, ...previous.filter((j) => j.id !== job.id)]);
      open(job);
    } catch (e) {
      notify(e.message);
    } finally {
      setStarting(false);
    }
  };
  const startMatch = async () => {
    setStarting(true);
    try {
      const match = await api("/api/matches", {
        method: "POST",
        body: JSON.stringify({ replay_id: selected }),
      });
      setMatches((previous) => [match, ...previous.filter((m) => m.id !== match.id)]);
      setJobs(await api("/api/jobs"));
      open(match);
    } catch (e) {
      notify(e.message);
    } finally {
      setStarting(false);
    }
  };
  const refresh = async () => {
    setRefreshing(true);
    try {
      await api("/api/replays/refresh", { method: "POST" });
      setReplays(await api("/api/replays"));
    } catch (e) {
      notify(e.message);
    } finally {
      setRefreshing(false);
    }
  };
  const imported = async (replay) => {
    setImporting(false);
    setReplays(await api("/api/replays"));
    setPage("workspace");
    await choose(replay);
  };
  const newReview = () => {
    setActiveId(null);
    localStorage.removeItem("aimguard:last-analysis");
    setPage("workspace");
  };
  const current =
    jobs.find((j) => j.id === activeId) || matches.find((m) => m.id === activeId);
  const historyItems = [...matches, ...jobs.filter((j) => !j.match_id)].sort((a, b) =>
    b.created.localeCompare(a.created),
  );
  const selectedReplay = replays.find((r) => r.id === selected);
  const busy = jobs.filter((j) => ["queued", "running"].includes(j.status));
  const maps = [...new Set(replays.map((r) => r.map).filter(Boolean))].sort();
  const files = useMemo(
    () =>
      replays.filter(
        (r) =>
          (map === "all" || r.map === map) &&
          `${r.name} ${r.map} ${r.folder}`.toLowerCase().includes(query.toLowerCase()),
      ),
    [replays, query, map],
  );
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <Brand />
        <div className="nav-label">WORKSPACE</div>
        <nav aria-label="Main navigation">
          {[
            ["workspace", Crosshair, "Replay analysis"],
            ["history", History, "Analysis history"],
            ["settings", Settings2, "Settings"],
          ].map(([key, Icon, label]) => (
            <button
              key={key}
              className={`nav-item ${page === key ? "active" : ""}`}
              onClick={() => setPage(key)}
              aria-current={page === key ? "page" : undefined}
              aria-label={label}
              title={label}
            >
              <Icon size={17} />
              <span>{label}</span>
              {key === "history" && <small>{historyItems.length || "—"}</small>}
            </button>
          ))}
        </nav>
        <div className="sidebar-note">
          <div className="tiny-crosshair">
            <Crosshair size={18} />
          </div>
          <h4>A closer look at the aim.</h4>
          <p>From replay telemetry to evidence you can inspect.</p>
        </div>
        <div className="sidebar-bottom">
          <div className="engine-line">
            <span className={`status-dot ${boot?.model.ready ? "" : "offline-dot"}`} />
            <span>Local engine</span>
            <small>v{boot?.model.version || "0.6"}</small>
          </div>
          <div className="privacy-line">
            <HardDrive size={12} /> Files stay on this device
          </div>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div className="breadcrumbs">
            WORKSPACE <span>/</span>{" "}
            <strong>
              {page === "history"
                ? "HISTORY"
                : page === "settings"
                  ? "SETTINGS"
                  : current?.kind === "match"
                    ? "MATCH REVIEW"
                    : current
                      ? "PLAYER REVIEW"
                      : "REPLAY ANALYSIS"}
            </strong>
          </div>
          <div className={`connection ${connected ? "" : "connection-lost"}`}>
            <span className="status-dot" />
            {connected ? "On this device" : "Disconnected"}
          </div>
        </header>
        <main>
          {!boot ? (
            <div className="boot-state">
              {connected ? (
                <>
                  <Spinner />
                  <span>Opening your workspace…</span>
                </>
              ) : (
                <>
                  <TriangleAlert size={22} />
                  <span>Keep the AimGuard launch window open.</span>
                  <button className="button secondary" onClick={() => location.reload()}>
                    Reconnect
                  </button>
                </>
              )}
            </div>
          ) : page === "settings" ? (
            <Settings boot={boot} count={replays.length} />
          ) : page === "history" ? (
            <HistoryPage jobs={historyItems} onOpen={open} onNew={newReview} />
          ) : current?.kind === "match" ? (
            <MatchReview
              match={current}
              onBack={newReview}
              onOpen={open}
              onCancel={async () => {
                try {
                  await api(`/api/matches/${current.id}/cancel`, { method: "POST" });
                  setMatches(await api("/api/matches"));
                  setJobs(await api("/api/jobs"));
                } catch (e) {
                  notify(e.message);
                }
              }}
            />
          ) : current ? (
            <Review
              job={current}
              onBack={() =>
                current.match_id
                  ? open(matches.find((m) => m.id === current.match_id))
                  : newReview()
              }
              backLabel={current.match_id ? "Match review" : "Replay workspace"}
              onCancel={async () => {
                try {
                  await api(`/api/jobs/${current.id}/cancel`, {
                    method: "POST",
                  });
                  setJobs(await api("/api/jobs"));
                } catch (e) {
                  notify(e.message);
                }
              }}
            />
          ) : (
            <>
              <div className="page-heading">
                <div>
                  <div className="eyebrow">THE REVIEW DESK</div>
                  <h1>
                    Replay analysis<span className="title-period">.</span>
                  </h1>
                  <p>Choose a local replay to start a player review.</p>
                </div>
                <button className="button primary" onClick={() => setImporting(true)}>
                  <Plus size={16} /> Add replay <kbd>⌘ O</kbd>
                </button>
              </div>
              {!boot.model.ready && (
                <div className="notice">
                  <TriangleAlert size={17} />
                  <div>
                    The analysis engine needs attention.{" "}
                    <button onClick={() => setPage("settings")}>Open settings</button> to
                    check the detector.
                  </div>
                </div>
              )}
              <div className="work-grid">
                <section className="panel library-panel">
                  <div className="panel-heading">
                    <h2>
                      Replay library <span className="count">{replays.length}</span>
                    </h2>
                    <button
                      className="icon-button"
                      title="Refresh local replay files"
                      onClick={refresh}
                      disabled={refreshing}
                    >
                      <RefreshCw size={15} className={refreshing ? "spin" : ""} />
                    </button>
                  </div>
                  <div className="library-controls">
                    <div className="search-box">
                      <Search size={15} />
                      <input
                        ref={searchRef}
                        aria-label="Search replay library"
                        value={query}
                        onChange={(e) => setQuery(e.target.value)}
                        placeholder="Find a replay…"
                      />
                      <kbd>⌘ K</kbd>
                    </div>
                    <div className="select-wrap compact">
                      <SlidersHorizontal size={14} />
                      <select
                        aria-label="Filter by map"
                        value={map}
                        onChange={(e) => setMap(e.target.value)}
                      >
                        <option value="all">All maps</option>
                        {maps.map((m) => (
                          <option key={m}>{m}</option>
                        ))}
                      </select>
                      <ChevronDown size={12} />
                    </div>
                  </div>
                  <div className="library-column-labels">
                    <span>REPLAY</span>
                    <span>SIZE</span>
                  </div>
                  <div className="replay-list">
                    {files.length ? (
                      files.map((replay) => (
                        <button
                          key={replay.id}
                          className={`replay-row ${selected === replay.id ? "selected" : ""}`}
                          onClick={() => choose(replay)}
                          title={replay.path}
                        >
                          <div className="map-tile">
                            {mapCode(replay.map)}
                            <span />
                          </div>
                          <div className="replay-copy">
                            <div>{replay.name}</div>
                            <span>
                              {replay.map || "Uninspected replay"}
                              <i /> {replay.folder}
                            </span>
                          </div>
                          <span className="file-size">{bytes(replay.size)}</span>
                          <ChevronRight size={14} className="row-chevron" />
                        </button>
                      ))
                    ) : (
                      <Empty
                        icon={FolderOpen}
                        title={query ? "No matching replays" : "Your library starts here"}
                      >
                        {query
                          ? "Try another filename or map."
                          : "Add a .dem file from your computer to begin."}
                      </Empty>
                    )}
                  </div>
                  <button className="library-add" onClick={() => setImporting(true)}>
                    <FilePlus2 size={16} /> Add a file or use its local path{" "}
                    <ArrowUpRight size={14} />
                  </button>
                  <div className="panel-footnote">
                    <Database size={12} /> {files.length}{" "}
                    {files.length === 1 ? "file" : "files"} in view{" "}
                    <span>CS2 · local files</span>
                  </div>
                </section>
                <section className="panel player-panel">
                  <div className="panel-heading">
                    <h2>Set up your review</h2>
                    <span className="step-label">01 — 02</span>
                  </div>
                  {!selectedReplay ? (
                    <Empty icon={Crosshair} title="Choose a replay">
                      Select a match from your library. Its players will appear here.
                    </Empty>
                  ) : (
                    <>
                      <div className="replay-detail">
                        <div className="replay-detail-label">
                          <MapPin size={13} />
                          {roster
                            ? maps.includes(selectedReplay.map)
                              ? selectedReplay.map
                              : roster.map.replace("de_", "").toUpperCase()
                            : selectedReplay.map || "CS2 replay"}
                        </div>
                        <h3 title={selectedReplay.name}>{selectedReplay.name}</h3>
                        <span>
                          <File size={12} />
                          {bytes(selectedReplay.size)}
                          <i />{" "}
                          {roster
                            ? `${roster.players.length} players`
                            : "Reading match details"}
                        </span>
                      </div>
                      <div className="roster-heading">
                        <span>SELECT A PLAYER</span>
                        {roster && <span>{roster.players.length} available</span>}
                      </div>
                      {inspection || (!roster && !inspectError) ? (
                        <div className="roster-loading">
                          <Spinner />
                          <span>Reading replay roster…</span>
                          <small>Large recordings may take a moment.</small>
                        </div>
                      ) : inspectError ? (
                        <div className="inline-error">
                          <TriangleAlert size={18} />
                          <h4>Couldn’t read this replay</h4>
                          <p>Try a different CS2 recording.</p>
                          <details>
                            <summary>Show details</summary>
                            <pre>{inspectError}</pre>
                          </details>
                        </div>
                      ) : (
                        <div className="roster-list">
                          {[...roster.players]
                            .sort((a, b) => (a.team || 9) - (b.team || 9))
                            .map((p) => (
                              <button
                                key={p.steamid}
                                className={`player-row ${p.steamid === player ? "selected" : ""}`}
                                onClick={() => setPlayer(p.steamid)}
                              >
                                <span className={`avatar team-${p.team}`}>
                                  {p.name.slice(0, 2).toUpperCase()}
                                </span>
                                <span className="player-copy">
                                  <strong>{p.name}</strong>
                                  <small>{p.steamid}</small>
                                </span>
                                <span className="team-label">
                                  {p.team === 2 ? "T" : p.team === 3 ? "CT" : "—"}
                                </span>
                                <span className="radio">
                                  {p.steamid === player && <span />}
                                </span>
                              </button>
                            ))}
                        </div>
                      )}
                      <div className="analyze-footer">
                        <button
                          className="button primary full"
                          disabled={!roster || !player || starting || !boot.model.ready}
                          onClick={start}
                        >
                          {starting ? (
                            <Spinner />
                          ) : (
                            <Play size={14} fill="currentColor" />
                          )}{" "}
                          Analyze player <ArrowRight size={16} />
                        </button>
                        <button
                          className="button secondary full match-start"
                          disabled={
                            !roster?.players?.length || starting || !boot.model.ready
                          }
                          onClick={startMatch}
                        >
                          Analyze all players <span>{roster?.players?.length || 0}</span>
                        </button>
                        <p>
                          <ShieldCheck size={12} /> Frozen detector ·{" "}
                          {boot.model.tickrate || 64} Hz analysis
                        </p>
                      </div>
                    </>
                  )}
                </section>
              </div>
              <section className="recent-section">
                <div className="section-heading">
                  <h2>Recent analyses</h2>
                  <button className="text-button" onClick={() => setPage("history")}>
                    View history <ArrowUpRight size={14} />
                  </button>
                </div>
                <JobTable jobs={historyItems.slice(0, 4)} onOpen={open} />
              </section>
            </>
          )}
        </main>
        <footer className="app-footer">
          <span>
            AIMGUARD <i /> LOCAL WORKSPACE
          </span>
          <span>Evidence before conclusions.</span>
        </footer>
      </div>
      {importing && (
        <ImportDialog onClose={() => setImporting(false)} onImported={imported} />
      )}
      {toast && (
        <div className="toast" role="status">
          <Info size={16} />
          <span>{toast}</span>
          <button
            className="icon-button"
            onClick={() => setToast("")}
            aria-label="Dismiss message"
          >
            <X size={14} />
          </button>
        </div>
      )}
    </div>
  );
}

createRoot(document.getElementById("root")).render(<App />);
