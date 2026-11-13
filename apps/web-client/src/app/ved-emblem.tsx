"use client";

import { useId } from "react";
import styles from "./ved-emblem.module.css";

export type EmblemState = "idle" | "thinking" | "speaking";

interface VedEmblemProps {
  state: EmblemState;
  size: number;
  className?: string;
}

const BEAM_TILT = "rotate(-22 512 512)";
const DASH_TILT = "rotate(40 512 512)";
const V_POINTS = "372,388 512,654 652,388";
const DOT_CENTER_Y = 300;
const DOT_RADIUS = 20;

export function VedEmblem({ state, size, className }: VedEmblemProps) {
  const scope = useId().replace(/:/g, "");
  const beamId = `${scope}-beam`;
  const coreId = `${scope}-core`;
  const glowId = `${scope}-glow`;
  const hazeId = `${scope}-haze`;
  const glowFilter = `url(#${glowId})`;

  return (
    <svg
      className={`${styles.emblem} ${className ?? ""}`}
      data-state={state}
      style={{ width: size, height: size }}
      viewBox="0 0 1024 1024"
      aria-hidden="true"
      focusable="false"
    >
      <defs>
        <linearGradient id={beamId} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#67e8f9" />
          <stop offset="1" stopColor="#3b82f6" />
        </linearGradient>
        <radialGradient id={coreId} cx="0.5" cy="0.5" r="0.5">
          <stop offset="0" stopColor="#0ea5e9" stopOpacity="0.35" />
          <stop offset="0.6" stopColor="#0369a1" stopOpacity="0.08" />
          <stop offset="1" stopColor="#000" stopOpacity="0" />
        </radialGradient>
        <filter id={glowId} x="-40%" y="-40%" width="180%" height="180%">
          <feGaussianBlur stdDeviation="10" result="soft" />
          <feMerge>
            <feMergeNode in="soft" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
        <filter id={hazeId} x="-100%" y="-100%" width="300%" height="300%">
          <feGaussianBlur stdDeviation="22" />
        </filter>
      </defs>

      <circle cx="512" cy="512" r="420" fill={`url(#${coreId})`} />

      <g className={styles.ticks}>
        <circle
          cx="512"
          cy="512"
          r="446"
          fill="none"
          stroke="#38bdf8"
          strokeOpacity="0.45"
          strokeWidth="10"
          strokeDasharray="3 21"
        />
      </g>

      <g transform={BEAM_TILT}>
        <g className={styles.segments}>
          <circle
            cx="512"
            cy="512"
            r="400"
            fill="none"
            stroke={`url(#${beamId})`}
            strokeWidth="16"
            strokeLinecap="round"
            strokeDasharray="380 70 140 70 600 70 120 1000"
            filter={glowFilter}
          />
        </g>
      </g>

      <circle
        cx="512"
        cy="512"
        r="340"
        fill="none"
        stroke="#0ea5e9"
        strokeOpacity="0.35"
        strokeWidth="4"
      />

      <g transform={DASH_TILT}>
        <g className={styles.dashes}>
          <circle
            cx="512"
            cy="512"
            r="300"
            fill="none"
            stroke="#7dd3fc"
            strokeOpacity="0.7"
            strokeWidth="8"
            strokeDasharray="60 34"
          />
        </g>
      </g>

      <g className={styles.v}>
        <polyline
          className={styles.vHaze}
          points={V_POINTS}
          fill="none"
          stroke="#38bdf8"
          strokeWidth="112"
          strokeLinejoin="miter"
          strokeLinecap="square"
          filter={`url(#${hazeId})`}
        />
        <polyline
          className={styles.vBright}
          points={V_POINTS}
          fill="none"
          stroke="#e0f7ff"
          strokeWidth="64"
          strokeLinejoin="miter"
          strokeLinecap="square"
          filter={glowFilter}
        />
      </g>

      <g className={styles.orbit}>
        <circle
          className={styles.dot}
          cx="512"
          cy={DOT_CENTER_Y}
          r={DOT_RADIUS}
          fill="#67e8f9"
          filter={glowFilter}
        />
      </g>
    </svg>
  );
}
