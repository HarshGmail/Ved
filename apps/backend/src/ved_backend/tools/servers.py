from mcp import StdioServerParameters
from mcp.client.stdio import get_default_environment

from ved_backend.config import Settings

REMINDERS = "reminders"
PEOPLE = "people"


def configured_servers(settings: Settings) -> dict[str, StdioServerParameters]:
    environment = {
        **get_default_environment(),
        "VED_DATABASE_URL": settings.database_url,
        "VED_TIMEZONE": settings.timezone,
    }
    return {
        REMINDERS: StdioServerParameters(
            command=settings.reminders_server_command,
            args=settings.reminders_server_args,
            cwd=settings.reminders_server_dir,
            env=environment,
        ),
        PEOPLE: StdioServerParameters(
            command=settings.people_server_command,
            args=settings.people_server_args,
            cwd=settings.people_server_dir,
            env=environment,
        ),
    }
