from mcp import StdioServerParameters
from mcp.client.stdio import get_default_environment

from ved_backend.config import Settings
from ved_backend.tools.toolbox import RemoteServer, ServerSpec

REMINDERS = "reminders"
PEOPLE = "people"
MEMORY = "memory"
WEB = "web"
PLAN = "plan"


def configured_servers(settings: Settings) -> dict[str, ServerSpec]:
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
    servers: dict[str, ServerSpec] = {}
    if settings.plan_configured:
        servers[PLAN] = RemoteServer(
            url=settings.plan_mcp_url, token=settings.plan_mcp_token
        )
    else:
        servers[REMINDERS] = StdioServerParameters(
            command=settings.reminders_server_command,
            args=settings.reminders_server_args,
            cwd=settings.reminders_server_dir,
            env=environment,
        )
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
