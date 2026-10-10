"use client";

import { useSearchParams } from "next/navigation";
import { useCallback } from "react";

export const CONVERSATION_PARAM = "c";

type HistoryMode = "push" | "replace";

function urlFor(conversationId: string | null): string {
  const url = new URL(window.location.href);
  if (conversationId) url.searchParams.set(CONVERSATION_PARAM, conversationId);
  else url.searchParams.delete(CONVERSATION_PARAM);
  return `${url.pathname}${url.search}${url.hash}`;
}

export function useConversationParam(): [
  string | null,
  (conversationId: string | null, mode: HistoryMode) => void,
] {
  const conversationId = useSearchParams().get(CONVERSATION_PARAM) || null;

  const setConversationId = useCallback(
    (next: string | null, mode: HistoryMode) => {
      const target = urlFor(next);
      if (mode === "push") window.history.pushState(null, "", target);
      else window.history.replaceState(null, "", target);
    },
    [],
  );

  return [conversationId, setConversationId];
}
