import logging
import uuid
from collections.abc import AsyncIterable, AsyncIterator
from contextlib import aclosing, asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.sse import EventSourceResponse, ServerSentEvent
from pydantic import BaseModel
from sqlalchemy import text

from ved_backend.access import require_access
from ved_backend.agent import Agent
from ved_backend.config import settings
from ved_backend.database import engine, session_factory
from ved_backend.documents import DocumentLibrary, DocumentNotFoundError
from ved_backend.extraction import UnsupportedDocumentError
from ved_backend.indexing import DocumentIndexer, MessageIndexer
from ved_backend.llm import build_embedder, build_provider
from ved_backend.llm.base import LLMRequestError, Message
from ved_backend.memory import ConversationNotFoundError, ConversationStore
from ved_backend.push import Notification, PushNotConfiguredError, PushService
from ved_backend.scheduler import ReminderScheduler
from ved_backend.schemas import (
    AcknowledgementEvent,
    AgentReply,
    AgentRequest,
    AgentTurn,
    ConversationList,
    ConversationStatus,
    ConversationSummary,
    ConversationTranscript,
    DocumentList,
    DocumentSummary,
    HealthStatus,
    MeResponse,
    PushStatus,
    PushSubscribeRequest,
    PushTestResult,
    PushUnsubscribeRequest,
    ServiceState,
    StreamErrorEvent,
    ThinkingEvent,
    TokenEvent,
    ToolFinishedEvent,
    ToolStartedEvent,
)
from ved_backend.tools.servers import configured_servers
from ved_backend.tools.toolbox import MCPToolbox
from ved_backend.turns import TurnItem, TurnRegistry
from ved_backend.uploads import (
    MULTIPART_OVERHEAD_BYTES,
    MalformedUploadError,
    UploadTooLargeError,
)
from ved_backend.users import CurrentUser, UserDirectory

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s | %(message)s",
)

logger = logging.getLogger(__name__)

NO_TOOLS_MESSAGE = "No MCP servers are connected, so Ved cannot act yet."
UNEXPECTED_STREAM_FAILURE = "Ved hit an unexpected error while answering."

DONE_EVENT = "done"
ERROR_EVENT = "error"
STREAM_EVENT_NAMES: dict[type[BaseModel], str] = {
    TokenEvent: "token",
    ThinkingEvent: "thinking",
    AcknowledgementEvent: "ack",
    ToolStartedEvent: "tool",
    ToolFinishedEvent: "tool_result",
}


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    toolbox = MCPToolbox(configured_servers(settings))
    await toolbox.connect()
    provider = build_provider(settings)

    application.state.toolbox = toolbox
    application.state.users = UserDirectory(session_factory)
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
    document_indexer = DocumentIndexer(
        session_factory, settings.documents_dir, embedder
    )
    scheduler = ReminderScheduler(
        session_factory,
        push,
        timezone=settings.timezone,
        poll_seconds=settings.scheduler_poll_seconds,
        birthday_reminder_time=settings.birthday_reminder_time,
        indexers=[
            background
            for background in (indexer, document_indexer)
            if background is not None
        ],
    )
    application.state.indexer = indexer
    application.state.document_indexer = document_indexer
    application.state.documents = DocumentLibrary(
        session_factory,
        settings.documents_dir,
        max_upload_bytes=settings.documents_max_upload_bytes,
    )
    application.state.push = push
    application.state.turns = TurnRegistry()
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
        await document_indexer.aclose()
        if indexer is not None:
            await indexer.aclose()
        if embedder is not None:
            await embedder.aclose()
        closer = getattr(provider, "aclose", None)
        if closer is not None:
            await closer()
        await toolbox.aclose()
        await engine.dispose()


app = FastAPI(
    title="Ved backend",
    version=settings.version,
    lifespan=lifespan,
    dependencies=[Depends(require_access)],
)

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


@app.get("/me")
async def read_me(user: CurrentUser) -> MeResponse:
    return MeResponse(email=user.email, name=user.name)


async def conversation_history(
    request: AgentRequest, user: CurrentUser
) -> list[Message]:
    toolbox: MCPToolbox = app.state.toolbox
    if not toolbox.tools:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=NO_TOOLS_MESSAGE,
        )

    if request.conversation_id is None:
        return []
    store: ConversationStore = app.state.conversations
    try:
        return await store.history(user.id, request.conversation_id)
    except ConversationNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(error)
        ) from error


History = Annotated[list[Message], Depends(conversation_history)]


async def save_turn(
    user_id: uuid.UUID, conversation_id: uuid.UUID, prompt: str, turn: AgentTurn
) -> AgentReply:
    store: ConversationStore = app.state.conversations
    await store.record_turn(
        user_id,
        conversation_id,
        prompt=prompt,
        answer=turn.text,
        model=turn.model,
        tool_calls=turn.tool_calls,
    )
    indexer: MessageIndexer | None = app.state.indexer
    if indexer is not None:
        indexer.trigger()
    return AgentReply(
        text=turn.text,
        model=turn.model,
        conversation_id=conversation_id,
        tool_calls=turn.tool_calls,
    )


async def record_reply(
    user_id: uuid.UUID, request: AgentRequest, turn: AgentTurn
) -> AgentReply:
    store: ConversationStore = app.state.conversations
    conversation_id = request.conversation_id or await store.start(
        user_id, request.prompt
    )
    return await save_turn(user_id, conversation_id, request.prompt, turn)


@app.post("/agent/message")
async def agent_message(
    request: AgentRequest, history: History, user: CurrentUser
) -> AgentReply:
    agent: Agent = app.state.agent
    try:
        turn = await agent.run(request.prompt, history, user_id=user.id)
    except LLMRequestError as error:
        logger.warning("LLM unreachable: %s", error)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        ) from error

    return await record_reply(user.id, request, turn)


async def ensure_turn_can_run(request: AgentRequest, user: CurrentUser) -> None:
    await conversation_history(request, user)


TurnGuard = Annotated[None, Depends(ensure_turn_can_run)]


async def stream_turn(
    user_id: uuid.UUID, request: AgentRequest
) -> AsyncIterator[TurnItem]:
    agent: Agent = app.state.agent
    store: ConversationStore = app.state.conversations
    try:
        history = (
            []
            if request.conversation_id is None
            else await store.history(user_id, request.conversation_id)
        )
        async with aclosing(
            agent.stream(request.prompt, history, user_id=user_id)
        ) as events:
            async for event in events:
                if isinstance(event, AgentTurn):
                    yield await record_reply(user_id, request, event)
                else:
                    yield event
    except LLMRequestError as error:
        logger.warning("LLM failed mid-stream: %s", error)
        yield StreamErrorEvent(detail=str(error))
    except Exception:
        logger.exception("Streaming reply failed")
        yield StreamErrorEvent(detail=UNEXPECTED_STREAM_FAILURE)


def server_sent_event(item: TurnItem) -> ServerSentEvent:
    if isinstance(item, AgentReply):
        return ServerSentEvent(event=DONE_EVENT, data=item)
    if isinstance(item, StreamErrorEvent):
        return ServerSentEvent(event=ERROR_EVENT, data=item)
    return ServerSentEvent(event=STREAM_EVENT_NAMES[type(item)], data=item)


@app.post("/agent/message/stream", response_class=EventSourceResponse)
async def agent_message_stream(
    request: AgentRequest, user: CurrentUser, _: TurnGuard
) -> AsyncIterable[ServerSentEvent]:
    turns: TurnRegistry = app.state.turns
    conversation_key = request.conversation_id or uuid.uuid4()
    items = turns.start(
        user.id, conversation_key, lambda: stream_turn(user.id, request)
    )
    while (item := await items.get()) is not None:
        yield server_sent_event(item)


@app.get("/push/status")
async def push_status(user: CurrentUser) -> PushStatus:
    push: PushService = app.state.push
    return PushStatus(
        configured=push.configured,
        public_key=push.public_key,
        subscriptions=await push.subscription_count(user.id),
    )


@app.post("/push/subscribe", status_code=status.HTTP_201_CREATED)
async def push_subscribe(
    request: PushSubscribeRequest, user: CurrentUser
) -> PushStatus:
    push: PushService = app.state.push
    if not push.configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(PushNotConfiguredError()),
        )
    await push.subscribe(
        user.id, request.endpoint, request.keys.model_dump(), request.label
    )
    return PushStatus(
        configured=True,
        public_key=push.public_key,
        subscriptions=await push.subscription_count(user.id),
    )


@app.post("/push/unsubscribe")
async def push_unsubscribe(
    request: PushUnsubscribeRequest, user: CurrentUser
) -> PushStatus:
    push: PushService = app.state.push
    await push.unsubscribe(user.id, request.endpoint)
    return PushStatus(
        configured=push.configured,
        public_key=push.public_key,
        subscriptions=await push.subscription_count(user.id),
    )


@app.post("/push/test")
async def push_test(user: CurrentUser) -> PushTestResult:
    push: PushService = app.state.push
    try:
        report = await push.send(
            user.id,
            Notification(
                title="Ved",
                body="Push is working. Reminders will arrive here.",
                tag="push-test",
            ),
        )
    except PushNotConfiguredError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)
        ) from error
    return PushTestResult(sent=report.sent, expired=report.expired)


@app.get("/conversations")
async def list_conversations(user: CurrentUser) -> ConversationList:
    store: ConversationStore = app.state.conversations
    rows = await store.recent_conversations(user.id, settings.conversation_list_limit)
    return ConversationList(
        conversations=[ConversationSummary.model_validate(row) for row in rows]
    )


@app.get("/conversations/{conversation_id}/status")
async def conversation_status(
    conversation_id: uuid.UUID, user: CurrentUser
) -> ConversationStatus:
    store: ConversationStore = app.state.conversations
    turns: TurnRegistry = app.state.turns
    try:
        await store.require_owned(user.id, conversation_id)
    except ConversationNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(error)
        ) from error
    return ConversationStatus(answering=turns.is_answering(user.id, conversation_id))


@app.get("/conversations/{conversation_id}")
async def read_conversation(
    conversation_id: uuid.UUID, user: CurrentUser
) -> ConversationTranscript:
    store: ConversationStore = app.state.conversations
    try:
        conversation = await store.transcript(user.id, conversation_id)
    except ConversationNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(error)
        ) from error
    return ConversationTranscript.model_validate(conversation)


def declared_length(request: Request) -> int | None:
    declared = request.headers.get("content-length", "")
    return int(declared) if declared.isdigit() else None


def reject_oversized_upload(request: Request, max_bytes: int) -> None:
    declared = declared_length(request)
    if declared is not None and declared > max_bytes + MULTIPART_OVERHEAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=str(UploadTooLargeError(max_bytes)),
        )


@app.post(
    "/documents",
    status_code=status.HTTP_201_CREATED,
    responses={status.HTTP_200_OK: {"description": "Already uploaded"}},
)
async def upload_document(
    request: Request, response: Response, user: CurrentUser
) -> DocumentSummary:
    library: DocumentLibrary = app.state.documents
    reject_oversized_upload(request, settings.documents_max_upload_bytes)
    try:
        stored = await library.upload(
            user.id, request.stream(), request.headers.get("content-type")
        )
    except UploadTooLargeError as error:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail=str(error)
        ) from error
    except UnsupportedDocumentError as error:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=str(error)
        ) from error
    except MalformedUploadError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)
        ) from error

    if stored.created:
        document_indexer: DocumentIndexer = app.state.document_indexer
        document_indexer.trigger()
    else:
        response.status_code = status.HTTP_200_OK
    return DocumentSummary.model_validate(stored.document)


@app.get("/documents")
async def list_documents(user: CurrentUser) -> DocumentList:
    library: DocumentLibrary = app.state.documents
    rows = await library.list(user.id)
    return DocumentList(documents=[DocumentSummary.model_validate(row) for row in rows])


@app.get("/documents/{document_id}")
async def read_document(document_id: uuid.UUID, user: CurrentUser) -> DocumentSummary:
    library: DocumentLibrary = app.state.documents
    try:
        document = await library.get(user.id, document_id)
    except DocumentNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(error)
        ) from error
    return DocumentSummary.model_validate(document)


@app.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(document_id: uuid.UUID, user: CurrentUser) -> None:
    library: DocumentLibrary = app.state.documents
    try:
        await library.delete(user.id, document_id)
    except DocumentNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(error)
        ) from error
