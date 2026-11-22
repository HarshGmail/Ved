"use client";

import { type ReactNode, useCallback, useEffect, useState } from "react";
import { connector, type FamilyNote, type FamilyOverview, type FamilyPerson } from "@/connector";
import { relativeTime } from "../relative-time";
import styles from "./what-ved-knows.module.css";

const LOADING_COPY = "Loading what Ved knows…";
const LOAD_FAILED_COPY = "Couldn't load this.";
const NO_FAMILY_COPY =
  "Ved doesn't know your family yet. The household admin can add people in home-admin.";
const NOT_RECOGNISED_COPY = "Ved doesn't know who you are yet.";
const ADMIN_NOTE_COPY = "Edited by the household admin";
const NO_NOTES_COPY =
  "No family notes yet. Tell Ved something is for everyone and it will show up here.";
const DELETE_FAILED_COPY = "Couldn't delete that note.";
const UNKNOWN_AUTHOR_COPY = "Someone";
const OWNER_LABEL = "Owner";
const OWNER_RELATION = "self";
const MONTHS = [
  "Jan",
  "Feb",
  "Mar",
  "Apr",
  "May",
  "Jun",
  "Jul",
  "Aug",
  "Sep",
  "Oct",
  "Nov",
  "Dec",
] as const;
const LANGUAGE_NAMES: Readonly<Record<string, string>> = {
  en: "English",
  te: "Telugu",
  hi: "Hindi",
};

interface Loaded {
  overview: FamilyOverview;
  notes: FamilyNote[];
  loadedAt: number;
}

function describe(error: unknown): string {
  return error instanceof Error ? error.message : "Something went wrong";
}

function relationLabel(person: FamilyPerson, ownerName: string | null): string | null {
  if (person.relation === OWNER_RELATION) return OWNER_LABEL;
  if (!person.relation) return null;
  return ownerName ? `${ownerName}'s ${person.relation}` : person.relation;
}

function birthdayLabel(person: FamilyPerson): string | null {
  if (person.birthday_month === null || person.birthday_day === null) return null;
  return `${person.birthday_day} ${MONTHS[person.birthday_month - 1]}`;
}

function languageLabel(code: string | null): string | null {
  if (!code) return null;
  return LANGUAGE_NAMES[code] ?? code;
}

function Detail({ label, value }: { label: string; value: string | null }) {
  if (!value) return null;
  return (
    <div className={styles.detail}>
      <dt className={styles.detailLabel}>{label}</dt>
      <dd className={styles.detailValue}>{value}</dd>
    </div>
  );
}

function Block({ id, heading, children }: { id: string; heading: string; children: ReactNode }) {
  return (
    <section className={styles.block} aria-labelledby={id}>
      <h3 id={id} className={styles.heading}>
        {heading}
      </h3>
      {children}
    </section>
  );
}

function YouBlock({ overview }: { overview: FamilyOverview }) {
  const { me, owner_name: ownerName } = overview;
  return (
    <Block id="knows-you" heading="Who Ved thinks you are">
      {me ? (
        <dl className={styles.details}>
          <Detail label="Name" value={me.name} />
          <Detail label="Relation" value={relationLabel(me, ownerName)} />
          <Detail label="Preferred language" value={languageLabel(me.language)} />
        </dl>
      ) : (
        <p className={styles.muted}>{NOT_RECOGNISED_COPY}</p>
      )}
      <p className={styles.hint}>{ADMIN_NOTE_COPY}</p>
    </Block>
  );
}

function FamilyBlock({ overview }: { overview: FamilyOverview }) {
  return (
    <Block id="knows-family" heading="Your family">
      <ul className={styles.list}>
        {overview.people.map((person) => {
          const details = [relationLabel(person, overview.owner_name), birthdayLabel(person)]
            .filter((detail): detail is string => detail !== null)
            .join(" · ");
          return (
            <li key={person.id} className={styles.item}>
              <span className={styles.itemTitle}>{person.name}</span>
              {person.aliases.length > 0 && (
                <span className={styles.itemMeta}>Also called {person.aliases.join(", ")}</span>
              )}
              {details && <span className={styles.itemMeta}>{details}</span>}
            </li>
          );
        })}
      </ul>
    </Block>
  );
}

function NoteCard({
  note,
  now,
  deleting,
  onDelete,
}: {
  note: FamilyNote;
  now: number;
  deleting: boolean;
  onDelete: () => void;
}) {
  return (
    <li className={styles.item}>
      <p className={styles.noteText}>{note.text}</p>
      <div className={styles.noteFoot}>
        <span className={styles.itemMeta}>
          {note.author_name ?? UNKNOWN_AUTHOR_COPY} ·{" "}
          <time dateTime={note.created_at}>{relativeTime(note.created_at, now)}</time>
        </span>
        {note.mine && (
          <button
            type="button"
            className={styles.danger}
            onClick={onDelete}
            disabled={deleting}
            aria-label="Delete this note"
          >
            {deleting ? "Deleting…" : "Delete"}
          </button>
        )}
      </div>
    </li>
  );
}

function NotesBlock({
  notes,
  now,
  deletingId,
  problem,
  onDelete,
}: {
  notes: FamilyNote[];
  now: number;
  deletingId: string | null;
  problem: string | null;
  onDelete: (note: FamilyNote) => void;
}) {
  return (
    <Block id="knows-notes" heading="Family notes">
      {notes.length === 0 ? (
        <p className={styles.muted}>{NO_NOTES_COPY}</p>
      ) : (
        <ul className={styles.list}>
          {notes.map((note) => (
            <NoteCard
              key={note.id}
              note={note}
              now={now}
              deleting={deletingId === note.id}
              onDelete={() => onDelete(note)}
            />
          ))}
        </ul>
      )}
      {problem && (
        <p className={styles.error} role="alert">
          {problem}
        </p>
      )}
    </Block>
  );
}

export function WhatVedKnows() {
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [loadProblem, setLoadProblem] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [deleteProblem, setDeleteProblem] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    Promise.all([
      connector.family({ signal: controller.signal }),
      connector.familyNotes({ signal: controller.signal }),
    ]).then(
      ([overview, listing]) =>
        setLoaded({ overview, notes: listing.notes, loadedAt: Date.now() }),
      (caught: unknown) => {
        if (!controller.signal.aborted) setLoadProblem(describe(caught));
      },
    );
    return () => controller.abort();
  }, []);

  const deleteNote = useCallback(async (note: FamilyNote) => {
    if (!window.confirm("Delete this note? Everyone in the family will lose it.")) return;
    setDeletingId(note.id);
    setDeleteProblem(null);
    try {
      await connector.deleteFamilyNote(note.id);
      setLoaded((current) =>
        current && { ...current, notes: current.notes.filter((entry) => entry.id !== note.id) },
      );
    } catch (caught: unknown) {
      setDeleteProblem(`${DELETE_FAILED_COPY} ${describe(caught)}`);
    } finally {
      setDeletingId(null);
    }
  }, []);

  if (loadProblem) {
    return (
      <p className={styles.muted}>
        {LOAD_FAILED_COPY} {loadProblem}
      </p>
    );
  }
  if (!loaded) return <p className={styles.muted}>{LOADING_COPY}</p>;

  const knowsFamily = loaded.overview.people.length > 0;

  return (
    <div className={styles.body}>
      {knowsFamily ? (
        <>
          <YouBlock overview={loaded.overview} />
          <FamilyBlock overview={loaded.overview} />
        </>
      ) : (
        <p className={styles.muted}>{NO_FAMILY_COPY}</p>
      )}
      <NotesBlock
        notes={loaded.notes}
        now={loaded.loadedAt}
        deletingId={deletingId}
        problem={deleteProblem}
        onDelete={deleteNote}
      />
    </div>
  );
}
