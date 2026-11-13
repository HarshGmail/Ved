import { Suspense } from "react";
import { Conversations } from "./conversations";
import styles from "./page.module.css";

export default function Home() {
  return (
    <main className={styles.main}>
      <Suspense>
        <Conversations />
      </Suspense>
    </main>
  );
}
