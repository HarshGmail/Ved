"use client";

import Link from "next/link";
import { type FormEvent, useCallback, useEffect, useState } from "react";
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

interface Draft {
  presetKey: string;
  label: string;
  name: string;
  url: string;
  token: string;
  help: string | null;
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
  return { presetKey: CUSTOM_KEY, label: "Custom MCP server", name: "", url: "", token: "", help: null };
}

function resultText(result: McpConnectionTest): string {
  if (result.ok) return `Connected · ${result.tool_count} tools`;
  return `Could not connect: ${result.error ?? "unknown error"}`;
}

export function ConnectionsPanel() {
  const [connections, setConnections] = useState<McpConnection[] | null>(null);
  const [presets, setPresets] = useState<McpConnectionPreset[]>([]);
  const [results, setResults] = useState<Record<string, McpConnectionTest>>({});
  const [busyId, setBusyId] = useState<string | null>(null);
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

  useEffect(() => {
    let active = true;
    connector
      .listConnections()
      .then((listing) => {
        if (active) setConnections(listing.connections);
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
  }, []);

  const runTest = useCallback(async (connectionId: string) => {
    setBusyId(connectionId);
    try {
      const result = await connector.testConnection(connectionId);
      setResults((current) => ({ ...current, [connectionId]: result }));
    } catch (caught: unknown) {
      setResults((current) => ({
        ...current,
        [connectionId]: { ok: false, tool_count: 0, error: describe(caught) },
      }));
    } finally {
      setBusyId(null);
    }
  }, []);

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
      } catch (caught: unknown) {
        setError(describe(caught));
      }
    },
    [],
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

  return (
    <main className={styles.page}>
      <nav className={styles.nav}>
        <Link href="/" className={styles.back}>
          ← Ved
        </Link>
      </nav>
      <h1 className={styles.title}>Connections</h1>
      <p className={styles.intro}>
        Link your own tools. Ved can use only the connections you turn on, and only you see them.
      </p>

      {error && <p role="alert" className={styles.error}>{error}</p>}

      {connections === null && !error && <p className={styles.muted}>Loading…</p>}

      {connections?.length === 0 && (
        <p className={styles.muted}>No connections yet.</p>
      )}

      <ul className={styles.list}>
        {connections?.map((connection) => (
          <li key={connection.id} className={styles.row}>
            <div className={styles.rowHead}>
              <div className={styles.identity}>
                <span className={styles.name}>{connection.name}</span>
                <span className={styles.url} title={connection.url}>
                  {connection.url}
                </span>
              </div>
              <button
                type="button"
                role="switch"
                aria-checked={connection.enabled}
                aria-label={`${connection.name} enabled`}
                className={styles.toggle}
                data-on={connection.enabled || undefined}
                onClick={() => toggle(connection)}
              >
                {connection.enabled ? "On" : "Off"}
              </button>
            </div>
            <div className={styles.actions}>
              <button
                type="button"
                className={styles.action}
                onClick={() => runTest(connection.id)}
                disabled={busyId === connection.id}
              >
                {busyId === connection.id ? "Testing…" : "Test"}
              </button>
              <button
                type="button"
                className={styles.action}
                onClick={() => remove(connection)}
              >
                Remove
              </button>
            </div>
            {results[connection.id] && (
              <p
                className={styles.result}
                data-ok={results[connection.id].ok || undefined}
                role="status"
              >
                {resultText(results[connection.id])}
              </p>
            )}
          </li>
        ))}
      </ul>

      {draft === null ? (
        <section className={styles.addSection} aria-label="Add a connection">
          <p className={styles.heading}>add a connection</p>
          <div className={styles.presetRow}>
            {presets.map((preset) => (
              <button
                key={preset.id}
                type="button"
                className={styles.action}
                onClick={() => setDraft(presetDraft(preset))}
              >
                {preset.label}
              </button>
            ))}
            <button
              type="button"
              className={styles.action}
              onClick={() => setDraft(customDraft())}
            >
              Custom MCP server
            </button>
          </div>
        </section>
      ) : (
        <form className={styles.form} onSubmit={submit} aria-label={draft.label}>
          <p className={styles.heading}>{draft.label}</p>
          {draft.help && <p className={styles.muted}>Get the token: {draft.help}</p>}
          <label className={styles.field}>
            <span>Name</span>
            <input
              className={styles.input}
              value={draft.name}
              onChange={(event) => updateDraft("name", event.target.value)}
              autoComplete="off"
              spellCheck={false}
              required
            />
          </label>
          <label className={styles.field}>
            <span>URL</span>
            <input
              className={styles.input}
              type="url"
              value={draft.url}
              onChange={(event) => updateDraft("url", event.target.value)}
              autoComplete="off"
              required
            />
          </label>
          <label className={styles.field}>
            <span>Token</span>
            <input
              className={styles.input}
              type="password"
              value={draft.token}
              onChange={(event) => updateDraft("token", event.target.value)}
              autoComplete="off"
              required
            />
          </label>
          {formError && <p role="alert" className={styles.error}>{formError}</p>}
          <div className={styles.actions}>
            <button type="submit" className={styles.action} disabled={saving}>
              {saving ? "Connecting…" : "Connect"}
            </button>
            <button
              type="button"
              className={styles.action}
              onClick={() => {
                setDraft(null);
                setFormError(null);
              }}
            >
              Cancel
            </button>
          </div>
        </form>
      )}
    </main>
  );
}
