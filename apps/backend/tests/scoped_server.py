from mcp.server.mcpserver import MCPServer

server = MCPServer("fake-scoped")


@server.tool(name="notes.list")
def list_notes(user_id: str, topic: str) -> str:
    return f"{user_id}|{topic}"


@server.tool(name="plain.echo")
def echo(text: str) -> str:
    return text


@server.tool(name="reminders.create")
def create_reminder(text: str) -> str:
    return f"reminder {text}"


if __name__ == "__main__":
    server.run()
