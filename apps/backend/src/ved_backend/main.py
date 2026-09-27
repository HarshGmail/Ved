import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from ved_backend.agent import Agent
from ved_backend.config import settings
from ved_backend.database import engine
from ved_backend.llm import build_provider
from ved_backend.llm.openai_compatible import LLMRequestError
from ved_backend.schemas import AgentReply, AgentRequest, HealthStatus, ServiceState
from ved_backend.tools.servers import configured_servers
from ved_backend.tools.toolbox import MCPToolbox

logger = logging.getLogger(__name__)

NO_TOOLS_MESSAGE = "No MCP servers are connected, so Ved cannot act yet."


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    toolbox = MCPToolbox(configured_servers(settings))
    await toolbox.connect()
    provider = build_provider(settings)

    application.state.toolbox = toolbox
    application.state.agent = Agent(
        provider,
        toolbox,
        max_tool_rounds=settings.agent_max_tool_rounds,
        timezone=settings.timezone,
    )
    logger.info("Agent ready on %s with %d tools", provider.model, len(toolbox.tools))
    try:
        yield
    finally:
        closer = getattr(provider, "aclose", None)
        if closer is not None:
            await closer()
        await toolbox.aclose()
        await engine.dispose()


app = FastAPI(title="Ved backend", version=settings.version, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def check_database() -> ServiceState:
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except Exception:
        logger.exception("Database health check failed")
        return "down"
    return "ok"


@app.get("/health")
async def health() -> HealthStatus:
    database = await check_database()
    return HealthStatus(
        status="ok" if database == "ok" else "degraded",
        version=settings.version,
        database=database,
    )


@app.post("/agent/message")
async def agent_message(request: AgentRequest) -> AgentReply:
    toolbox: MCPToolbox = app.state.toolbox
    if not toolbox.tools:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=NO_TOOLS_MESSAGE,
        )

    agent: Agent = app.state.agent
    try:
        return await agent.run(request.prompt)
    except LLMRequestError as error:
        logger.warning("LLM unreachable: %s", error)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        ) from error
