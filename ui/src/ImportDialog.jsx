import React, { useEffect, useRef, useState } from "react";
import {
  Check,
  FilePlus2,
  Folder,
  FolderOpen,
  HardDrive,
  TriangleAlert,
  Upload,
  X,
} from "lucide-react";
import { api, getSessionToken } from "./client.js";
import { Spinner } from "./components.jsx";

export default function ImportDialog({ onClose, onImported }) {
  const [mode, setMode] = useState("file"),
    [path, setPath] = useState(""),
    [error, setError] = useState(""),
    [progress, setProgress] = useState(null),
    [dragging, setDragging] = useState(false);
  const dialogRef = useRef(null),
    fileRef = useRef(null),
    requestRef = useRef(null);
  useEffect(() => {
    const previous = document.activeElement;
    dialogRef.current?.querySelector("button")?.focus();
    return () => previous?.focus();
  }, []);
  useEffect(() => {
    const close = (e) => {
      if (e.key === "Escape" && progress == null) onClose();
      if (e.key === "Tab") {
        const controls = [
          ...dialogRef.current.querySelectorAll(
            "button:not(:disabled), input:not([hidden]):not(:disabled), a[href]",
          ),
        ];
        const first = controls[0],
          last = controls.at(-1);
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last?.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first?.focus();
        }
      }
    };
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [progress]);
  const upload = (file) => {
    if (!file) return;
    if (!file.name.toLowerCase().endsWith(".dem"))
      return setError("Choose a CS2 .dem replay.");
    if (file.size > 2 * 1024 ** 3)
      return setError("Replay files must be 2 GiB or smaller. Use a shorter recording.");
    setError("");
    setProgress(0);
    const xhr = new XMLHttpRequest();
    requestRef.current = xhr;
    xhr.open("POST", `/api/replays/upload?name=${encodeURIComponent(file.name)}`);
    xhr.setRequestHeader("X-AimGuard-Token", getSessionToken());
    xhr.setRequestHeader("Content-Type", "application/octet-stream");
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) setProgress(Math.round((e.loaded / e.total) * 100));
    };
    xhr.onerror = () => {
      setProgress(null);
      setError("The local connection was interrupted.");
    };
    xhr.onabort = () => {
      setProgress(null);
      setError("Import cancelled.");
    };
    xhr.onload = () => {
      setProgress(null);
      try {
        const data = JSON.parse(xhr.responseText);
        if (xhr.status < 300) onImported(data);
        else
          setError(
            typeof data.detail === "string"
              ? data.detail
              : "Could not import this replay.",
          );
      } catch {
        setError("Could not import this replay. Check the launch window and try again.");
      }
    };
    xhr.send(file);
  };
  const local = async (e) => {
    e.preventDefault();
    setError("");
    setProgress(0);
    try {
      await onImported(
        await api("/api/replays/local", {
          method: "POST",
          body: JSON.stringify({ path }),
        }),
      );
    } catch (e) {
      setError(e.message);
    } finally {
      setProgress(null);
    }
  };
  return (
    <div
      className="modal-overlay"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget && progress == null) onClose();
      }}
    >
      <section
        ref={dialogRef}
        className="import-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="import-title"
      >
        <div className="modal-heading">
          <div>
            <div className="eyebrow">ADD TO YOUR WORKSPACE</div>
            <h2 id="import-title">Open a replay.</h2>
          </div>
          <button
            className="icon-button"
            onClick={() => {
              requestRef.current?.abort();
              onClose();
            }}
            aria-label="Close import dialog"
          >
            <X size={20} />
          </button>
        </div>
        <div className="segmented import-tabs">
          <button
            className={mode === "file" ? "active" : ""}
            disabled={progress != null}
            onClick={() => setMode("file")}
          >
            <Upload size={14} /> Import file
          </button>
          <button
            className={mode === "path" ? "active" : ""}
            disabled={progress != null}
            onClick={() => setMode("path")}
          >
            <Folder size={14} /> Use local path
          </button>
        </div>
        {mode === "file" ? (
          <>
            <input
              ref={fileRef}
              type="file"
              accept=".dem"
              hidden
              onChange={(e) => upload(e.target.files?.[0])}
            />
            <button
              className={`drop-zone ${dragging ? "dragging" : ""}`}
              disabled={progress != null}
              onClick={() => fileRef.current.click()}
              onDragOver={(e) => {
                e.preventDefault();
                setDragging(true);
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={(e) => {
                e.preventDefault();
                setDragging(false);
                upload(e.dataTransfer.files[0]);
              }}
            >
              <span className="drop-icon">
                <FilePlus2 size={30} strokeWidth={1.2} />
              </span>
              <strong>Drop a replay here</strong>
              <span>or click to choose a file</span>
              <small>CS2 .dem files · up to 2 GiB</small>
            </button>
            <p className="modal-description">
              A copy stays in your local workspace. Nothing leaves this computer.
            </p>
          </>
        ) : (
          <form onSubmit={local}>
            <label className="field-label" htmlFor="local-path">
              REPLAY FILE PATH
            </label>
            <input
              autoFocus
              className="path-input"
              id="local-path"
              placeholder="/Users/you/Downloads/match.dem"
              value={path}
              onChange={(e) => setPath(e.target.value)}
              disabled={progress != null}
            />
            <p className="modal-description">
              Reads the existing file directly, without making another copy.
            </p>
            <button className="button primary full" disabled={!path || progress != null}>
              {progress != null ? <Spinner /> : <FolderOpen size={16} />} Open local
              replay
            </button>
          </form>
        )}
        {progress != null && (
          <div className="upload-state">
            <div>
              <Spinner />
              <span>
                {mode === "path"
                  ? "Opening file…"
                  : progress === 100
                    ? "Finishing local import…"
                    : `Copying to workspace · ${progress}%`}
              </span>
            </div>
            <div className="progress-track">
              <span style={{ width: `${mode === "path" ? 30 : progress}%` }} />
            </div>
          </div>
        )}
        {error && (
          <div className="form-error" role="alert">
            <TriangleAlert size={15} />
            {error}
          </div>
        )}
        <div className="modal-foot">
          <HardDrive size={13} /> LOCAL FILES ONLY
        </div>
      </section>
    </div>
  );
}
