import { useEffect, useState } from "react";
import { connector, type Me } from "@/connector";

export function usePerson(): Me | null {
  const [person, setPerson] = useState<Me | null>(null);

  useEffect(() => {
    const controller = new AbortController();

    connector
      .me({ signal: controller.signal })
      .then(setPerson)
      .catch(() => setPerson(null));

    return () => controller.abort();
  }, []);

  return person;
}

export function firstNameOf(person: Me | null): string | null {
  return person?.name?.trim().split(/\s+/)[0] || null;
}
