"use client";

import { useEffect, useState } from "react";
import { connector } from "@/connector";
import styles from "./signed-in-as.module.css";

export function SignedInAs() {
  const [email, setEmail] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();

    connector
      .me({ signal: controller.signal })
      .then((me) => setEmail(me.email))
      .catch(() => setEmail(null));

    return () => controller.abort();
  }, []);

  if (email === null) return null;
  return <p className={styles.email}>{email}</p>;
}
