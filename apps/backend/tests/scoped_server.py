from mcp.server.mcpserver import MCPServer

server = MCPServer("fake-scoped")


@server.tool(name="notes.list")
def list_notes(user_id: str, topic: str) -> str:
    return f"{user_id}|{topic}"


@server.tool(name="plain.echo")
def echo(text: str) -> str:
    return text


if __name__ == "__main__":
    server.run()
