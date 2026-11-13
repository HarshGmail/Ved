import Link from "next/link";
import { Suspense } from "react";
import { BackendStatus } from "./backend-status";
import { Conversations } from "./conversations";
import { PlugIcon } from "./icons";
import { Notifications } from "./notifications";
import styles from "./page.module.css";
import { SignedInAs } from "./signed-in-as";
import { VedEmblem } from "./ved-emblem";

const HERO_EMBLEM_SIZE = 140;

export default function Home() {
  return (
    <main className={styles.main}>
      <VedEmblem state="idle" size={HERO_EMBLEM_SIZE} />
      <h1 className={styles.title}>Ved</h1>
      <p className={styles.subtitle}>Personal AI operating layer</p>
      <p className={styles.phase}>Phase 2 — memory and reminders</p>
      <SignedInAs />
      <Link href="/connections" className={styles.connections}>
        <PlugIcon className={styles.connectionsIcon} />
        Connections
      </Link>
      <BackendStatus />
      <Notifications />
      <Suspense>
        <Conversations />
      </Suspense>
    </main>
  );
}
