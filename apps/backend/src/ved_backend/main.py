import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from ved_backend.agent import Agent
from ved_backend.config import settings
from ved_backend.database import engine, session_factory
from ved_backend.llm import build_provider
from ved_backend.llm.base import Message
from ved_backend.llm.openai_compatible import LLMRequestError
from ved_backend.memory import ConversationNotFoundError, ConversationStore
from ved_backend.schemas import (
    AgentReply,
    AgentRequest,
    ConversationList,
    ConversationSummary,
    ConversationTranscript,
    HealthStatus,
    ServiceState,
)
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
    application.state.conversations = ConversationStore(
        session_factory, history_limit=settings.conversation_history_limit
    )
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
    store: ConversationStore = app.state.conversations

    try:
        history: list[Message] = (
            []
            if request.conversation_id is None
            else await store.history(request.conversation_id)
        )
    except ConversationNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(error)
        ) from error

    try:
        reply = await agent.run(request.prompt, history)
    except LLMRequestError as error:
        logger.warning("LLM unreachable: %s", error)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        ) from error

    conversation_id = request.conversation_id or await store.start(request.prompt)
    await store.record_turn(
        conversation_id,
        prompt=request.prompt,
        answer=reply.text,
        model=reply.model,
        tool_calls=reply.tool_calls,
    )
    return AgentReply(
        text=reply.text,
        model=reply.model,
        conversation_id=conversation_id,
        tool_calls=reply.tool_calls,
    )


@app.get("/conversations")
async def list_conversations() -> ConversationList:
    store: ConversationStore = app.state.conversations
    rows = await store.recent_conversations(settings.conversation_list_limit)
    return ConversationList(
        conversations=[ConversationSummary.model_validate(row) for row in rows]
    )


@app.get("/conversations/{conversation_id}")
async def read_conversation(conversation_id: uuid.UUID) -> ConversationTranscript:
    store: ConversationStore = app.state.conversations
    try:
        conversation = await store.transcript(conversation_id)
    except ConversationNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(error)
        ) from error
    return ConversationTranscript.model_validate(conversation)
