"use client";

import { type FormEvent, useEffect, useState } from "react";
import { type ClaudeUsage, connector } from "@/connector";
import styles from "./claude-usage.module.css";

const MAX_BALANCE_USD = 10_000;
const LOW_SHARE = 0.3;
const CRITICAL_SHARE = 0.1;
const PERCENT = 100;
const CENTS = 100;
const USD = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });
const SET_DATE = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short" });
const CHECKING_COPY = "Checking usage…";
const LOAD_FAILED_COPY = "Couldn't load Claude usage.";
const LOCAL_MODEL_COPY = "Ved is using the local model on noddy — no cost.";
const ENTER_BALANCE_COPY = "Enter your Anthropic balance to see what's left";
const BALANCE_HINT_COPY = "Copy the balance from console.anthropic.com → Billing";
const BALANCE_RANGE_COPY = `Enter a balance from $0 to $${MAX_BALANCE_USD.toLocaleString("en-US")}.`;
const UPDATE_BALANCE_LABEL = "Update balance";
const SAVE_LABEL = "Save";
const CANCEL_LABEL = "Cancel";
const BALANCE_INPUT_ID = "claude-balance";

type UsageTone = "healthy" | "low" | "critical";

function describe(error: unknown): string {
  return error instanceof Error ? error.message : "Something went wrong";
}

function formatUsd(amount: number): string {
  return USD.format(amount);
}

function parseBalance(text: string): number | null {
  const trimmed = text.trim();
  const amount = Number(trimmed);
  if (trimmed === "" || !Number.isFinite(amount)) return null;
  if (amount < 0 || amount > MAX_BALANCE_USD) return null;
  return Math.round(amount * CENTS) / CENTS;
}

function remainingShare(remaining: number, balance: number): number {
  if (balance <= 0) return 0;
  return Math.min(Math.max(remaining / balance, 0), 1);
}

function usageTone(share: number): UsageTone {
  if (share < CRITICAL_SHARE) return "critical";
  if (share < LOW_SHARE) return "low";
  return "healthy";
}

function messagesLabel(count: number): string {
  return `${count} ${count === 1 ? "message" : "messages"}`;
}

function Stats({ usage }: { usage: ClaudeUsage }) {
  return (
    <div className={styles.stats}>
      <p className={styles.stat}>
        Today {formatUsd(usage.today_usd)} · {messagesLabel(usage.today_messages)}
      </p>
      <p className={styles.stat}>This month {formatUsd(usage.month_usd)}</p>
    </div>
  );
}

function BalanceSummary({
  balance,
  remaining,
  setAt,
}: {
  balance: number;
  remaining: number;
  setAt: string | null;
}) {
  const share = remainingShare(remaining, balance);
  const percent = Math.round(share * PERCENT);
  const setOn = setAt ? ` set ${SET_DATE.format(new Date(setAt))}` : "";

  return (
    <div className={styles.summary}>
      <p className={styles.headline}>{formatUsd(remaining)} left</p>
      <p className={styles.muted}>
        of {formatUsd(balance)} balance{setOn}
      </p>
      <div
        className={styles.track}
        role="progressbar"
        aria-label="Credit left"
        aria-valuemin={0}
        aria-valuemax={PERCENT}
        aria-valuenow={percent}
        aria-valuetext={`${percent}% left`}
      >
        <div
          className={styles.fill}
          data-tone={usageTone(share)}
          style={{ width: `${percent}%` }}
        />
      </div>
    </div>
  );
}

function SpentOnly({ usage }: { usage: ClaudeUsage }) {
  return (
    <div className={styles.summary}>
      <p className={styles.headline}>
        Spent {formatUsd(usage.spent_since_balance_usd)} so far
      </p>
      {usage.can_edit && <p className={styles.muted}>{ENTER_BALANCE_COPY}</p>}
    </div>
  );
}

function BalanceForm({
  usage,
  onSaved,
  onCancel,
}: {
  usage: ClaudeUsage;
  onSaved: (next: ClaudeUsage) => void;
  onCancel: () => void;
}) {
  const [draft, setDraft] = useState(
    usage.balance_usd === null ? "" : usage.balance_usd.toFixed(2),
  );
  const [saving, setSaving] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const amount = parseBalance(draft);
    if (amount === null) {
      setProblem(BALANCE_RANGE_COPY);
      return;
    }
    setSaving(true);
    setProblem(null);
    try {
      onSaved(await connector.setClaudeBalance(amount));
    } catch (error) {
      setProblem(describe(error));
      setSaving(false);
    }
  }

  return (
    <form className={styles.form} onSubmit={save}>
      <label className={styles.label} htmlFor={BALANCE_INPUT_ID}>
        Anthropic balance
      </label>
      <div className={styles.inputRow}>
        <span className={styles.prefix} aria-hidden="true">
          $
        </span>
        <input
          id={BALANCE_INPUT_ID}
          className={styles.input}
          type="number"
          inputMode="decimal"
          min={0}
          max={MAX_BALANCE_USD}
          step="0.01"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          required
          autoFocus
        />
      </div>
      <p className={styles.hint}>{BALANCE_HINT_COPY}</p>
      {problem && (
        <p className={styles.error} role="alert">
          {problem}
        </p>
      )}
      <div className={styles.actions}>
        <button className={styles.primary} type="submit" disabled={saving}>
          {SAVE_LABEL}
        </button>
        <button
          className={styles.secondary}
          type="button"
          onClick={onCancel}
          disabled={saving}
        >
          {CANCEL_LABEL}
        </button>
      </div>
    </form>
  );
}

export function ClaudeUsageCard() {
  const [usage, setUsage] = useState<ClaudeUsage | null>(null);
  const [loadProblem, setLoadProblem] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);

  useEffect(() => {
    let active = true;
    connector.claudeUsage().then(
      (next) => {
        if (active) setUsage(next);
      },
      (error: unknown) => {
        if (active) setLoadProblem(describe(error));
      },
    );
    return () => {
      active = false;
    };
  }, []);

  if (loadProblem) {
    return (
      <p className={styles.muted}>
        {LOAD_FAILED_COPY} {loadProblem}
      </p>
    );
  }
  if (!usage) return <p className={styles.muted}>{CHECKING_COPY}</p>;
  if (!usage.tracking) return <p className={styles.muted}>{LOCAL_MODEL_COPY}</p>;

  const { balance_usd: balance, remaining_usd: remaining } = usage;

  return (
    <div className={styles.body}>
      {balance !== null && remaining !== null ? (
        <BalanceSummary
          balance={balance}
          remaining={remaining}
          setAt={usage.balance_set_at}
        />
      ) : (
        <SpentOnly usage={usage} />
      )}
      <Stats usage={usage} />
      <p className={styles.model}>{usage.model}</p>
      {usage.can_edit &&
        (editing ? (
          <BalanceForm
            usage={usage}
            onSaved={(next) => {
              setUsage(next);
              setEditing(false);
            }}
            onCancel={() => setEditing(false)}
          />
        ) : (
          <button
            className={styles.secondary}
            type="button"
            onClick={() => setEditing(true)}
          >
            {UPDATE_BALANCE_LABEL}
          </button>
        ))}
    </div>
  );
}
