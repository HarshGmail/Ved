import { BackendStatus } from "./backend-status";
import { Chat } from "./chat";
import { Notifications } from "./notifications";
import styles from "./page.module.css";

export default function Home() {
  return (
    <main className={styles.main}>
      <h1 className={styles.title}>Ved</h1>
      <p className={styles.subtitle}>Personal AI operating layer</p>
      <p className={styles.phase}>Phase 2 — memory and reminders</p>
      <BackendStatus />
      <Notifications />
      <Chat />
    </main>
  );
}
