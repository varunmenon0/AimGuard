import React, { useEffect, useMemo, useRef, useState } from "react";
import { Activity } from "lucide-react";

export default function Trajectory({ curve, tab }) {
  const [hover, setHover] = useState(null);
  const svgRef = useRef(null);
  useEffect(() => setHover(null), [curve, tab]);
  const { data, series, unit, caption } = useMemo(() => {
    if (tab === "angles") {
      const first = curve.points[0] || {};
      return {
        data: curve.points.map((p) => ({
          ...p,
          yaw: p.yaw - first.yaw,
          pitch: p.pitch - first.pitch,
        })),
        series: [
          { key: "yaw", label: "Yaw Δ", color: "#8ed5c0" },
          { key: "pitch", label: "Pitch Δ", color: "#d6b681" },
        ],
        unit: "°",
        caption:
          "Angles relative to window start. Shot markers use recorded fire events.",
      };
    }
    if (tab === "speed")
      return {
        data: curve.points,
        series: [{ key: "speed", label: "Angular speed", color: "#9fc6df" }],
        unit: "°/s",
        caption: "Speed derived from recorded view angles and actual tick spacing.",
      };
    if (tab === "error")
      return {
        data: curve.tracking,
        series: [
          {
            key: "error",
            label: "Horizontal alignment error",
            color: "#d6b681",
          },
        ],
        unit: "°",
        caption:
          "Alignment to the geometric opponent candidate; visibility is not verified.",
      };
    return {
      data: curve.tracking,
      series: [
        { key: "yaw_rate", label: "View yaw", color: "#8ed5c0" },
        { key: "bearing_rate", label: "Opponent bearing", color: "#9ba7b7" },
      ],
      unit: "°/s",
      caption:
        "View yaw and geometric opponent bearing. The candidate may not be visible.",
    };
  }, [curve, tab]);
  const width = 800,
    height = 280,
    left = 60,
    right = 20,
    top = 22,
    bottom = 36,
    plotWidth = width - left - right,
    plotHeight = height - top - bottom;
  const times = data.map((p) => p.t).filter(Number.isFinite),
    values = data.flatMap((p) => series.map((s) => p[s.key])).filter(Number.isFinite);
  const xmin = Math.min(-0.01, ...times),
    xmax = Math.max(0.01, ...times);
  let ymin = Math.min(0, ...values),
    ymax = Math.max(0, ...values);
  const margin = Math.max((ymax - ymin) * 0.14, 0.5);
  ymin -= margin;
  ymax += margin;
  const x = (t) => left + ((t - xmin) / (xmax - xmin)) * plotWidth,
    y = (v) => top + ((ymax - v) / (ymax - ymin)) * plotHeight;
  const path = (key) => {
    let drawing = false;
    return data
      .map((p) => {
        if (p.break_before) drawing = false;
        if (!Number.isFinite(p[key])) {
          drawing = false;
          return "";
        }
        const command = drawing ? "L" : "M";
        drawing = true;
        return `${command}${x(p.t).toFixed(2)},${y(p[key]).toFixed(2)}`;
      })
      .join(" ");
  };
  const format = (v) =>
    Math.abs(v) >= 100 ? v.toFixed(0) : Math.abs(v) >= 10 ? v.toFixed(1) : v.toFixed(2);
  const onMove = (e) => {
    const box = svgRef.current.getBoundingClientRect();
    const px = ((e.clientX - box.left) / box.width) * width;
    const time = xmin + ((px - left) / plotWidth) * (xmax - xmin);
    let nearest = null;
    for (const p of data)
      if (!nearest || Math.abs(p.t - time) < Math.abs(nearest.t - time)) nearest = p;
    setHover(nearest);
  };
  if (!values.length)
    return (
      <div className="chart-placeholder">
        <Activity size={25} />
        <p>No supported tracking samples in this window.</p>
      </div>
    );
  return (
    <div className="trajectory">
      <div className="chart-legend">
        {series.map((s) => (
          <span key={s.key}>
            <i style={{ background: s.color }} />
            {s.label}
          </span>
        ))}
        <span className="pre-shot-key">
          <i />
          Pre-shot interval
        </span>
      </div>
      <div className="svg-container">
        <svg
          ref={svgRef}
          viewBox={`0 0 ${width} ${height}`}
          onMouseMove={onMove}
          onMouseLeave={() => setHover(null)}
          aria-label={`Recorded ${tab} trajectory`}
          role="img"
        >
          <defs>
            <clipPath id="plotclip">
              <rect x={left} y={top} width={plotWidth} height={plotHeight} />
            </clipPath>
          </defs>
          <rect
            x={x(Math.max(xmin, -0.2))}
            y={top}
            width={Math.max(0, x(Math.min(0, xmax)) - x(Math.max(xmin, -0.2)))}
            height={plotHeight}
            fill="#88c7ae"
            opacity=".035"
          />
          {Array.from({ length: 5 }, (_, i) => {
            const value = ymin + ((ymax - ymin) * i) / 4;
            return (
              <g key={i}>
                <line
                  x1={left}
                  x2={width - right}
                  y1={y(value)}
                  y2={y(value)}
                  stroke="#263033"
                  strokeDasharray="3 5"
                />
                <text
                  x={left - 12}
                  y={y(value) + 4}
                  textAnchor="end"
                  className="axis-text"
                >
                  {format(value)}
                </text>
              </g>
            );
          })}
          {Array.from({ length: 6 }, (_, i) => {
            const t = xmin + ((xmax - xmin) * i) / 5;
            return (
              <text
                key={i}
                x={x(t)}
                y={height - 14}
                textAnchor="middle"
                className="axis-text"
              >
                {t.toFixed(2)}s
              </text>
            );
          })}
          <text x={left} y={12} className="axis-text">
            {unit}
          </text>
          <g clipPath="url(#plotclip)">
            <line
              x1={left}
              x2={width - right}
              y1={y(0)}
              y2={y(0)}
              stroke="#546163"
              opacity=".6"
            />
            {curve.shots.map((t, i) => (
              <g key={i}>
                <line
                  x1={x(t)}
                  x2={x(t)}
                  y1={top}
                  y2={height - bottom}
                  stroke="#c9b58c"
                  strokeDasharray="3 5"
                  opacity=".36"
                />
                <rect
                  x={x(t) - 2}
                  y={height - bottom - 5}
                  width="4"
                  height="5"
                  fill="#c9b58c"
                />
              </g>
            ))}
            {series.map((s) => (
              <path
                key={s.key}
                d={path(s.key)}
                fill="none"
                stroke={s.color}
                strokeWidth="1.8"
                strokeLinejoin="round"
                strokeLinecap="round"
              />
            ))}
            {hover && (
              <>
                <line
                  x1={x(hover.t)}
                  x2={x(hover.t)}
                  y1={top}
                  y2={height - bottom}
                  stroke="#c8d5d1"
                  opacity=".35"
                />
                {series.map(
                  (s) =>
                    Number.isFinite(hover[s.key]) && (
                      <circle
                        key={s.key}
                        cx={x(hover.t)}
                        cy={y(hover[s.key])}
                        r="3"
                        fill={s.color}
                        stroke="#151d1f"
                        strokeWidth="2"
                      />
                    ),
                )}
              </>
            )}
          </g>
        </svg>
        {hover && (
          <div className="chart-tooltip">
            <strong>{hover.t.toFixed(3)}s from first shot</strong>
            {series.map((s) => (
              <span key={s.key}>
                <i style={{ background: s.color }} />
                {s.label}
                <code>
                  {Number.isFinite(hover[s.key])
                    ? `${hover[s.key].toFixed(2)} ${unit}`
                    : "—"}
                </code>
              </span>
            ))}
          </div>
        )}
      </div>
      <div className="chart-caption">
        <span className="shot-key" /> Shot event <span className="caption-divider" />{" "}
        {caption}
      </div>
    </div>
  );
}
