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
from ved_backend.indexing import MessageIndexer
from ved_backend.llm import build_embedder, build_provider
from ved_backend.llm.base import Message
from ved_backend.llm.openai_compatible import LLMRequestError
from ved_backend.memory import ConversationNotFoundError, ConversationStore
from ved_backend.push import Notification, PushNotConfiguredError, PushService
from ved_backend.scheduler import ReminderScheduler
from ved_backend.schemas import (
    AgentReply,
    AgentRequest,
    ConversationList,
    ConversationSummary,
    ConversationTranscript,
    HealthStatus,
    PushStatus,
    PushSubscribeRequest,
    PushTestResult,
    PushUnsubscribeRequest,
    ServiceState,
)
from ved_backend.tools.servers import configured_servers
from ved_backend.tools.toolbox import MCPToolbox

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s | %(message)s",
)

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
    push = PushService(
        session_factory,
        public_key=settings.vapid_public_key,
        private_key=settings.vapid_private_key,
        subject=settings.vapid_subject,
    )
    embedder = build_embedder(settings)
    indexer = None if embedder is None else MessageIndexer(session_factory, embedder)
    scheduler = ReminderScheduler(
        session_factory,
        push,
        timezone=settings.timezone,
        poll_seconds=settings.scheduler_poll_seconds,
        birthday_reminder_time=settings.birthday_reminder_time,
        indexer=indexer,
    )
    application.state.indexer = indexer
    application.state.push = push
    application.state.scheduler = scheduler
    application.state.agent = Agent(
        provider,
        toolbox,
        max_tool_rounds=settings.agent_max_tool_rounds,
        timezone=settings.timezone,
    )
    logger.info("Agent ready on %s with %d tools", provider.model, len(toolbox.tools))
    if not push.configured:
        logger.warning("Push is not configured — due reminders will only be logged")
    scheduler.start()
    try:
        yield
    finally:
        await scheduler.stop()
        if indexer is not None:
            await indexer.aclose()
        if embedder is not None:
            await embedder.aclose()
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
    indexer: MessageIndexer | None = app.state.indexer
    if indexer is not None:
        indexer.trigger()
    return AgentReply(
        text=reply.text,
        model=reply.model,
        conversation_id=conversation_id,
        tool_calls=reply.tool_calls,
    )


@app.get("/push/status")
async def push_status() -> PushStatus:
    push: PushService = app.state.push
    return PushStatus(
        configured=push.configured,
        public_key=push.public_key,
        subscriptions=await push.subscription_count(),
    )


@app.post("/push/subscribe", status_code=status.HTTP_201_CREATED)
async def push_subscribe(request: PushSubscribeRequest) -> PushStatus:
    push: PushService = app.state.push
    if not push.configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(PushNotConfiguredError()),
        )
    await push.subscribe(request.endpoint, request.keys.model_dump(), request.label)
    return PushStatus(
        configured=True,
        public_key=push.public_key,
        subscriptions=await push.subscription_count(),
    )


@app.post("/push/unsubscribe")
async def push_unsubscribe(request: PushUnsubscribeRequest) -> PushStatus:
    push: PushService = app.state.push
    await push.unsubscribe(request.endpoint)
    return PushStatus(
        configured=push.configured,
        public_key=push.public_key,
        subscriptions=await push.subscription_count(),
    )


@app.post("/push/test")
async def push_test() -> PushTestResult:
    push: PushService = app.state.push
    try:
        report = await push.send(
            Notification(
                title="Ved",
                body="Push is working. Reminders will arrive here.",
                tag="push-test",
            )
        )
    except PushNotConfiguredError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)
        ) from error
    return PushTestResult(sent=report.sent, expired=report.expired)


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
