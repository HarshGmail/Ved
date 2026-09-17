import type { ConnectorConfig } from "./config";

export interface StreamHandlers<TMessage> {
  onMessage: (message: TMessage) => void;
  onOpen?: () => void;
  onError?: (error: unknown) => void;
  onClose?: (event: { code: number; reason: string }) => void;
}

export interface StreamHandle {
  send: (payload: unknown) => void;
  close: () => void;
}

function toWebSocketUrl(baseUrl: string, path: string): string {
  const url = new URL(path.replace(/^\//, ""), baseUrl.endsWith("/") ? baseUrl : `${baseUrl}/`);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  return url.toString();
}

export function createStreamClient(config: ConnectorConfig) {
  return function openStream<TMessage>(
    path: string,
    handlers: StreamHandlers<TMessage>,
  ): StreamHandle {
    const socket = new WebSocket(toWebSocketUrl(config.baseUrl, path));

    socket.addEventListener("open", () => handlers.onOpen?.());
    socket.addEventListener("error", (event) => handlers.onError?.(event));
    socket.addEventListener("close", (event) =>
      handlers.onClose?.({ code: event.code, reason: event.reason }),
    );
    socket.addEventListener("message", (event) => {
      try {
        handlers.onMessage(JSON.parse(event.data as string) as TMessage);
      } catch (error) {
        handlers.onError?.(error);
      }
    });

    return {
      send: (payload) => socket.send(JSON.stringify(payload)),
      close: () => socket.close(),
    };
  };
}

export type StreamClient = ReturnType<typeof createStreamClient>;
