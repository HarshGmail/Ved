"use client";

import { type FormEvent, type ReactNode, useCallback, useEffect, useState } from "react";
import {
  connector,
  type McpConnection,
  type McpConnectionPreset,
  type McpConnectionTest,
} from "@/connector";
import styles from "./connections.module.css";

const NAME_PATTERN = /^[a-z0-9]+(-[a-z0-9]+)*$/;
const NAME_MIN_LENGTH = 2;
const NAME_MAX_LENGTH = 20;
const RESERVED_NAMES = new Set(["memory", "documents", "web", "people", "reminders"]);
const CUSTOM_KEY = "custom";
const CUSTOM_LABEL = "Custom MCP server";
const CUSTOM_DESCRIPTION = "Any MCP server that takes a token";
const URL_MARKER_LABELS: ReadonlyArray<readonly [marker: string, label: string]> = [
  ["family-planner", "Plan"],
  ["plan.", "Plan"],
  ["my-finances", "MyFinances"],
];
const KNOWN_APP_HUES: Readonly<Record<string, number>> = { Plan: 215, MyFinances: 150 };
const HUE_WHEEL_DEGREES = 360;
const BADGE_SATURATION = "55%";
const BADGE_LIGHTNESS = "40%";

interface Draft {
  presetKey: string;
  label: string;
  name: string;
  url: string;
  token: string;
  help: string | null;
}

type StatusTone = "off" | "checking" | "ok" | "error";

interface ConnectionStatus {
  tone: StatusTone;
  text: string;
}

function describe(error: unknown): string {
  return error instanceof Error ? error.message : "Request failed";
}

function nameProblem(name: string): string | null {
  if (name.length < NAME_MIN_LENGTH || name.length > NAME_MAX_LENGTH || !NAME_PATTERN.test(name)) {
    return "Name: 2 to 20 lowercase letters or digits, with single dashes, such as plan";
  }
  if (RESERVED_NAMES.has(name)) return `Name: ${name} is reserved for Ved's own tools`;
  return null;
}

function urlProblem(url: string): string | null {
  return /^https?:\/\/[^/\s]+/i.test(url.trim()) ? null : "URL: start with http:// or https://";
}

function draftProblem(draft: Draft): string | null {
  if (draft.token.trim() === "") return "Token: paste the token from the other app";
  return nameProblem(draft.name) ?? urlProblem(draft.url);
}

function presetDraft(preset: McpConnectionPreset): Draft {
  return {
    presetKey: preset.id,
    label: preset.label,
    name: preset.name,
    url: preset.url,
    token: "",
    help: preset.help,
  };
}

function customDraft(): Draft {
  return { presetKey: CUSTOM_KEY, label: CUSTOM_LABEL, name: "", url: "", token: "", help: null };
}

function friendlyLabel(connection: McpConnection, presets: McpConnectionPreset[]): string {
  const preset = presets.find((candidate) => candidate.url === connection.url);
  if (preset) return preset.label;
  const marked = URL_MARKER_LABELS.find(([marker]) => connection.url.includes(marker));
  return marked ? marked[1] : connection.name;
}

function toolsLabel(count: number): string {
  return `${count} ${count === 1 ? "tool" : "tools"}`;
}

function connectionStatus(
  connection: McpConnection,
  result: McpConnectionTest | undefined,
  checking: boolean,
): ConnectionStatus {
  if (!connection.enabled) return { tone: "off", text: "Off · Ved won't use it" };
  if (checking || !result) return { tone: "checking", text: "Checking…" };
  if (result.ok) return { tone: "ok", text: `Connected · ${toolsLabel(result.tool_count)}` };
  return { tone: "error", text: `Couldn't connect: ${result.error ?? "unknown error"}` };
}

function hueFor(label: string): number {
  const known = KNOWN_APP_HUES[label];
  if (known !== undefined) return known;
  let hash = 0;
  for (const character of label) {
    hash = (hash * 31 + character.charCodeAt(0)) % HUE_WHEEL_DEGREES;
  }
  return hash;
}

function badgeColor(label: string): string {
  return `hsl(${hueFor(label)} ${BADGE_SATURATION} ${BADGE_LIGHTNESS})`;
}

function withId(ids: ReadonlySet<string>, id: string): ReadonlySet<string> {
  return new Set(ids).add(id);
}

function withoutId(ids: ReadonlySet<string>, id: string): ReadonlySet<string> {
  const remaining = new Set(ids);
  remaining.delete(id);
  return remaining;
}

function AppBadge({ label }: { label: string }) {
  return (
    <span className={styles.badge} aria-hidden="true" style={{ backgroundColor: badgeColor(label) }}>
      {label.charAt(0).toUpperCase()}
    </span>
  );
}

function StatusLine({ status }: { status: ConnectionStatus }) {
  return (
    <p className={styles.status} data-tone={status.tone} role="status">
      <span className={styles.dot} aria-hidden="true" />
      {status.text}
    </p>
  );
}

function Switch({ label, on, onToggle }: { label: string; on: boolean; onToggle: () => void }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      aria-label={`${label} enabled`}
      className={styles.switch}
      data-on={on || undefined}
      onClick={onToggle}
    >
      <span className={styles.track}>
        <span className={styles.knob} />
      </span>
    </button>
  );
}

interface ConnectionCardProps {
  connection: McpConnection;
  label: string;
  result: McpConnectionTest | undefined;
  checking: boolean;
  onToggle: () => void;
  onTest: () => void;
  onRemove: () => void;
}

function ConnectionCard({
  connection,
  label,
  result,
  checking,
  onToggle,
  onTest,
  onRemove,
}: ConnectionCardProps) {
  return (
    <li className={styles.card}>
      <div className={styles.cardTop}>
        <AppBadge label={label} />
        <div className={styles.cardText}>
          <span className={styles.cardLabel}>{label}</span>
          <span className={styles.cardMeta} title={connection.url}>
            {connection.name} · {connection.url}
          </span>
        </div>
        <Switch label={label} on={connection.enabled} onToggle={onToggle} />
      </div>
      <div className={styles.cardFoot}>
        <StatusLine status={connectionStatus(connection, result, checking)} />
        <div className={styles.cardActions}>
          {connection.enabled && (
            <button
              type="button"
              className={styles.textButton}
              onClick={onTest}
              disabled={checking}
            >
              {checking ? "Testing…" : "Test again"}
            </button>
          )}
          <button type="button" className={`${styles.textButton} ${styles.danger}`} onClick={onRemove}>
            Remove
          </button>
        </div>
      </div>
    </li>
  );
}

interface DraftFormProps {
  draft: Draft;
  saving: boolean;
  formError: string | null;
  onFieldChange: (field: "name" | "url" | "token", value: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  onCancel: () => void;
}

function DraftForm({ draft, saving, formError, onFieldChange, onSubmit, onCancel }: DraftFormProps) {
  const nameField = (
    <label className={styles.field}>
      <span>Name</span>
      <input
        className={styles.input}
        value={draft.name}
        onChange={(event) => onFieldChange("name", event.target.value)}
        autoComplete="off"
        spellCheck={false}
        required
      />
    </label>
  );
  const urlField = (
    <label className={styles.field}>
      <span>URL</span>
      <input
        className={styles.input}
        type="url"
        value={draft.url}
        onChange={(event) => onFieldChange("url", event.target.value)}
        autoComplete="off"
        required
      />
    </label>
  );
  const tokenField = (
    <label className={styles.field}>
      <span>Token</span>
      <input
        className={styles.input}
        type="password"
        value={draft.token}
        onChange={(event) => onFieldChange("token", event.target.value)}
        autoComplete="off"
        required
      />
    </label>
  );
  const isPreset = draft.presetKey !== CUSTOM_KEY;

  return (
    <form className={styles.form} onSubmit={onSubmit} aria-labelledby="draft-heading">
      <h3 id="draft-heading" className={styles.formHeading}>
        {draft.label}
      </h3>
      {isPreset ? (
        <>
          {tokenField}
          {draft.help && <p className={styles.hint}>Get the token: {draft.help}</p>}
          <details className={styles.advanced}>
            <summary className={styles.advancedSummary}>Advanced</summary>
            <div className={styles.advancedFields}>
              {nameField}
              {urlField}
            </div>
          </details>
        </>
      ) : (
        <>
          {nameField}
          {urlField}
          {tokenField}
        </>
      )}
      {formError && <p role="alert" className={styles.error}>{formError}</p>}
      <div className={styles.formActions}>
        <button type="submit" className={styles.primary} disabled={saving}>
          {saving ? "Connecting…" : "Connect"}
        </button>
        <button type="button" className={styles.secondary} onClick={onCancel}>
          Cancel
        </button>
      </div>
    </form>
  );
}

function Section({ id, heading, children }: { id: string; heading: string; children: ReactNode }) {
  return (
    <section aria-labelledby={id} className={styles.section}>
      <h2 id={id} className={styles.heading}>
        {heading}
      </h2>
      {children}
    </section>
  );
}

export function ConnectionsPanel() {
  const [connections, setConnections] = useState<McpConnection[] | null>(null);
  const [presets, setPresets] = useState<McpConnectionPreset[]>([]);
  const [results, setResults] = useState<Record<string, McpConnectionTest>>({});
  const [testingIds, setTestingIds] = useState<ReadonlySet<string>>(() => new Set());
  const [draft, setDraft] = useState<Draft | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(
    () =>
      connector
        .listConnections()
        .then((listing) => setConnections(listing.connections))
        .catch((caught: unknown) => setError(describe(caught))),
    [],
  );

  const runTest = useCallback(async (connectionId: string) => {
    setTestingIds((current) => withId(current, connectionId));
    try {
      const result = await connector.testConnection(connectionId);
      setResults((current) => ({ ...current, [connectionId]: result }));
    } catch (caught: unknown) {
      setResults((current) => ({
        ...current,
        [connectionId]: { ok: false, tool_count: 0, error: describe(caught) },
      }));
    } finally {
      setTestingIds((current) => withoutId(current, connectionId));
    }
  }, []);

  useEffect(() => {
    let active = true;
    connector
      .listConnections()
      .then((listing) => {
        if (!active) return;
        setConnections(listing.connections);
        listing.connections
          .filter((connection) => connection.enabled)
          .forEach((connection) => runTest(connection.id));
      })
      .catch((caught: unknown) => {
        if (active) setError(describe(caught));
      });
    connector
      .listConnectionPresets()
      .then((listing) => {
        if (active) setPresets(listing.presets);
      })
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, [runTest]);

  const toggle = useCallback(
    async (connection: McpConnection) => {
      setError(null);
      try {
        const updated = await connector.updateConnection(connection.id, {
          enabled: !connection.enabled,
        });
        setConnections((current) =>
          current?.map((row) => (row.id === updated.id ? updated : row)) ?? current,
        );
        if (updated.enabled) await runTest(updated.id);
      } catch (caught: unknown) {
        setError(describe(caught));
      }
    },
    [runTest],
  );

  const remove = useCallback(
    async (connection: McpConnection) => {
      setError(null);
      try {
        await connector.deleteConnection(connection.id);
        setResults((current) => {
          const remaining = { ...current };
          delete remaining[connection.id];
          return remaining;
        });
        await refresh();
      } catch (caught: unknown) {
        setError(describe(caught));
      }
    },
    [refresh],
  );

  const submit = useCallback(
    async (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      if (!draft) return;
      const problem = draftProblem(draft);
      if (problem) {
        setFormError(problem);
        return;
      }
      setSaving(true);
      setFormError(null);
      try {
        const created = await connector.createConnection({
          name: draft.name.trim(),
          url: draft.url.trim(),
          token: draft.token,
        });
        setDraft(null);
        await refresh();
        await runTest(created.id);
      } catch (caught: unknown) {
        setFormError(describe(caught));
      } finally {
        setSaving(false);
      }
    },
    [draft, refresh, runTest],
  );

  const updateDraft = (field: "name" | "url" | "token", value: string) =>
    setDraft((current) => (current ? { ...current, [field]: value } : current));

  const closeDraft = () => {
    setDraft(null);
    setFormError(null);
  };

  const labelOf = (connection: McpConnection) => friendlyLabel(connection, presets);

  const requestRemove = (connection: McpConnection) => {
    if (window.confirm(`Remove ${labelOf(connection)}? Ved will stop using it.`)) {
      remove(connection);
    }
  };

  const connectedUrls = new Set(connections?.map((connection) => connection.url));
  const availablePresets = presets.filter((preset) => !connectedUrls.has(preset.url));

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <p className={styles.intro}>
          Link your own tools. Ved can use only the connections you turn on, and only you see them.
        </p>
      </header>

      {error && <p role="alert" className={styles.error}>{error}</p>}

      <Section id="your-connections" heading="Your connections">
        {connections === null && !error && <p className={styles.muted}>Loading…</p>}
        {connections?.length === 0 && (
          <p className={styles.empty}>
            No connections yet. Connect Plan or MyFinances so Ved can read your tasks and money.
          </p>
        )}
        <ul className={styles.stack}>
          {connections?.map((connection) => (
            <ConnectionCard
              key={connection.id}
              connection={connection}
              label={labelOf(connection)}
              result={results[connection.id]}
              checking={testingIds.has(connection.id)}
              onToggle={() => toggle(connection)}
              onTest={() => runTest(connection.id)}
              onRemove={() => requestRemove(connection)}
            />
          ))}
        </ul>
      </Section>

      <Section id="add-connection" heading="Add a connection">
        {draft === null ? (
          <ul className={styles.stack}>
            {availablePresets.map((preset) => (
              <li key={preset.id}>
                <button
                  type="button"
                  className={styles.choice}
                  onClick={() => setDraft(presetDraft(preset))}
                >
                  <AppBadge label={preset.label} />
                  <span className={styles.cardText}>
                    <span className={styles.cardLabel}>{preset.label}</span>
                    <span className={styles.cardMeta}>{preset.help}</span>
                  </span>
                </button>
              </li>
            ))}
            <li>
              <button type="button" className={styles.choice} onClick={() => setDraft(customDraft())}>
                <AppBadge label={CUSTOM_LABEL} />
                <span className={styles.cardText}>
                  <span className={styles.cardLabel}>{CUSTOM_LABEL}</span>
                  <span className={styles.cardMeta}>{CUSTOM_DESCRIPTION}</span>
                </span>
              </button>
            </li>
          </ul>
        ) : (
          <DraftForm
            draft={draft}
            saving={saving}
            formError={formError}
            onFieldChange={updateDraft}
            onSubmit={submit}
            onCancel={closeDraft}
          />
        )}
      </Section>
    </div>
  );
}
