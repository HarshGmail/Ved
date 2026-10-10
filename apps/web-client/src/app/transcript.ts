import type { AgentReply, ConversationTranscript, TranscriptMessage } from "@/connector";

export type TranscriptTurn =
  | { role: "user"; text: string }
  | { role: "ved"; reply: AgentReply };

function toTurn(message: TranscriptMessage, conversationId: string): TranscriptTurn {
  if (message.role === "user") return { role: "user", text: message.text };
  return {
    role: "ved",
    reply: {
      text: message.text,
      model: message.model ?? "",
      conversation_id: conversationId,
      tool_calls: message.tool_calls,
    },
  };
}

export function transcriptToTurns(transcript: ConversationTranscript): TranscriptTurn[] {
  return transcript.messages.map((message) => toTurn(message, transcript.id));
}
