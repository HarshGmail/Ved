import argparse
import asyncio

CHUNK_BYTES = 64 * 1024


async def pipe(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        while chunk := await reader.read(CHUNK_BYTES):
            writer.write(chunk)
            await writer.drain()
    except ConnectionError:
        pass
    finally:
        writer.close()


def handler(target_host: str, target_port: int):
    async def relay(
        client_reader: asyncio.StreamReader, client_writer: asyncio.StreamWriter
    ) -> None:
        try:
            upstream_reader, upstream_writer = await asyncio.open_connection(
                target_host, target_port
            )
        except OSError:
            client_writer.close()
            return
        await asyncio.gather(
            pipe(client_reader, upstream_writer),
            pipe(upstream_reader, client_writer),
        )

    return relay


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Accept connections on [::1]:PORT and relay them to 127.0.0.1:PORT."
    )
    parser.add_argument("port", type=int)
    args = parser.parse_args()

    server = await asyncio.start_server(
        handler("127.0.0.1", args.port), host="::1", port=args.port
    )
    print(f"relaying [::1]:{args.port} -> 127.0.0.1:{args.port}", flush=True)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
