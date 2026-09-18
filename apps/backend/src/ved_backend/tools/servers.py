from mcp import StdioServerParameters
from mcp.client.stdio import get_default_environment

from ved_backend.config import Settings

REMINDERS = "reminders"


def configured_servers(settings: Settings) -> dict[str, StdioServerParameters]:
    return {
        REMINDERS: StdioServerParameters(
            command=settings.reminders_server_command,
            args=settings.reminders_server_args,
            cwd=settings.reminders_server_dir,
            env={
                **get_default_environment(),
                "VED_DATABASE_URL": settings.database_url,
            },
        )
    }
