from mcp import StdioServerParameters
from mcp.client.stdio import get_default_environment

from ved_backend.config import Settings
from ved_backend.llm import ANTHROPIC
from ved_backend.tools.toolbox import CONNECTION_TOOL_LIMIT, REMINDERS

PEOPLE = "people"
MEMORY = "memory"
WEB = "web"
ANTHROPIC_CONNECTION_TOOL_LIMIT = 40


def exposed_tools_for(settings: Settings) -> list[str]:
    if settings.llm_provider == ANTHROPIC:
        return []
    return settings.exposed_tools


def connection_tool_limit_for(settings: Settings) -> int:
    if settings.llm_provider == ANTHROPIC:
        return ANTHROPIC_CONNECTION_TOOL_LIMIT
    return CONNECTION_TOOL_LIMIT


def configured_servers(settings: Settings) -> dict[str, StdioServerParameters]:
    environment = {
        **get_default_environment(),
        "VED_DATABASE_URL": settings.database_url,
        "VED_TIMEZONE": settings.timezone,
    }
    memory_environment = {
        **environment,
        "VED_LLM_BASE_URL": settings.llm_base_url,
        "VED_EMBEDDING_MODEL": settings.embedding_model,
        "VED_EMBEDDING_DIMENSIONS": str(settings.embedding_dimensions),
        "VED_EMBEDDING_TIMEOUT_SECONDS": str(settings.embedding_timeout_seconds),
        "VED_EMBEDDING_QUERY_PREFIX": settings.embedding_query_prefix,
        **({"VED_LLM_API_KEY": settings.llm_api_key} if settings.llm_api_key else {}),
    }
    web_environment = {
        **get_default_environment(),
        "VED_SEARCH_PROVIDER": settings.search_provider,
        "VED_SEARXNG_URL": settings.searxng_url,
    }
    servers: dict[str, StdioServerParameters] = {
        REMINDERS: StdioServerParameters(
            command=settings.reminders_server_command,
            args=settings.reminders_server_args,
            cwd=settings.reminders_server_dir,
            env=environment,
        ),
    }
    servers[PEOPLE] = StdioServerParameters(
        command=settings.people_server_command,
        args=settings.people_server_args,
        cwd=settings.people_server_dir,
        env=environment,
    )
    servers[MEMORY] = StdioServerParameters(
        command=settings.memory_server_command,
        args=settings.memory_server_args,
        cwd=settings.memory_server_dir,
        env=memory_environment,
    )
    servers[WEB] = StdioServerParameters(
        command=settings.web_server_command,
        args=settings.web_server_args,
        cwd=settings.web_server_dir,
        env=web_environment,
    )
    return servers
