import type { ReactNode } from "react";

interface IconProps {
  className?: string;
}

function StrokeIcon({ className, children }: IconProps & { children: ReactNode }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {children}
    </svg>
  );
}

export function PlugIcon({ className }: IconProps) {
  return (
    <StrokeIcon className={className}>
      <path d="M9 2v6M15 2v6M6 8h12v4a6 6 0 0 1-12 0V8zM12 18v4" />
    </StrokeIcon>
  );
}

export function ChevronLeftIcon({ className }: IconProps) {
  return (
    <StrokeIcon className={className}>
      <polyline points="15 18 9 12 15 6" />
    </StrokeIcon>
  );
}
