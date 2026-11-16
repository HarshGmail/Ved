"use client";

import type { ReactNode } from "react";
import styles from "./settings.module.css";

export function formatRate(rate: number): string {
  return `${rate.toFixed(1)}×`;
}

export function ToggleRow({
  label,
  checked,
  onChange,
}: {
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
}) {
  return (
    <label className={styles.switchRow}>
      <span>{label}</span>
      <input
        className={styles.switchInput}
        type="checkbox"
        role="switch"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
      />
      <span className={styles.switchTrack} aria-hidden="true" />
    </label>
  );
}

export function Field({ label, children }: { label: ReactNode; children: ReactNode }) {
  return (
    <label className={styles.field}>
      <span className={styles.fieldLabel}>{label}</span>
      {children}
    </label>
  );
}

export function RangeField({
  label,
  value,
  range,
  format,
  onChange,
}: {
  label: string;
  value: number;
  range: { min: number; max: number; step: number };
  format: (value: number) => string;
  onChange: (value: number) => void;
}) {
  return (
    <Field
      label={
        <>
          {label} <output className={styles.fieldValue}>{format(value)}</output>
        </>
      }
    >
      <input
        className={styles.slider}
        type="range"
        min={range.min}
        max={range.max}
        step={range.step}
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
      />
    </Field>
  );
}
