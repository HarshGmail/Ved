import styles from "./launch-splash.module.css";

export function LaunchSplash() {
  return (
    <div className={styles.overlay} aria-hidden="true">
      <svg
        className={styles.mark}
        viewBox="0 0 1024 1024"
        focusable="false"
      >
        <defs>
          <linearGradient id="launch-beam" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor="#67e8f9" />
            <stop offset="1" stopColor="#3b82f6" />
          </linearGradient>
          <radialGradient id="launch-core" cx="0.5" cy="0.5" r="0.5">
            <stop offset="0" stopColor="#0ea5e9" stopOpacity="0.35" />
            <stop offset="0.6" stopColor="#0369a1" stopOpacity="0.08" />
            <stop offset="1" stopColor="#000" stopOpacity="0" />
          </radialGradient>
          <filter id="launch-glow" x="-40%" y="-40%" width="180%" height="180%">
            <feGaussianBlur stdDeviation="10" result="soft" />
            <feMerge>
              <feMergeNode in="soft" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
          <filter id="launch-haze" x="-100%" y="-100%" width="300%" height="300%">
            <feGaussianBlur stdDeviation="22" />
          </filter>
        </defs>

        <circle cx="512" cy="512" r="420" fill="url(#launch-core)" />

        <g className={styles.rings}>
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
          <g transform="rotate(-22 512 512)">
            <circle
              cx="512"
              cy="512"
              r="400"
              fill="none"
              stroke="url(#launch-beam)"
              strokeWidth="16"
              strokeLinecap="round"
              strokeDasharray="380 70 140 70 600 70 120 1000"
              filter="url(#launch-glow)"
            />
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
          <g transform="rotate(40 512 512)">
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

        <g className={styles.letter}>
          <polyline
            className={styles.haze}
            points="372,388 512,654 652,388"
            fill="none"
            stroke="#38bdf8"
            strokeWidth="112"
            strokeLinejoin="miter"
            strokeLinecap="square"
            filter="url(#launch-haze)"
          />
          <polyline
            className={styles.bright}
            points="372,388 512,654 652,388"
            fill="none"
            stroke="#e0f7ff"
            strokeWidth="64"
            strokeLinejoin="miter"
            strokeLinecap="square"
            filter="url(#launch-glow)"
          />
          <circle cx="512" cy="300" r="20" fill="#67e8f9" filter="url(#launch-glow)" />
        </g>
      </svg>
    </div>
  );
}
