import logging
import uuid
from collections.abc import AsyncIterable, AsyncIterator
from contextlib import aclosing, asynccontextmanager
from datetime import UTC, datetime
from typing import Annotated

from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.sse import EventSourceResponse, ServerSentEvent
from pydantic import BaseModel
from sqlalchemy import text
from starlette.background import BackgroundTask
from ved_db import MCPConnection, User

from ved_backend.access import require_access
from ved_backend.agent import Agent
from ved_backend.config import MEBIBYTE, settings
from ved_backend.connections import (
    PRESETS,
    ConnectionNameTakenError,
    ConnectionNotFoundError,
    ConnectionsDisabledError,
    ConnectionStore,
    probe,
)
from ved_backend.database import engine, session_factory
from ved_backend.documents import DocumentLibrary, DocumentNotFoundError
from ved_backend.extraction import UnsupportedDocumentError
from ved_backend.family import (
    FamilyDirectory,
    FamilyPerson,
    build_family_directory,
)
from ved_backend.family_notes import (
    FamilyNoteNotFoundError,
    FamilyNoteStore,
    NotNoteAuthorError,
)
from ved_backend.indexing import DocumentIndexer, MessageIndexer
from ved_backend.llm import ANTHROPIC, build_embedder, build_provider
from ved_backend.llm.base import LLMProvider, LLMRequestError, Message
from ved_backend.memory import ConversationNotFoundError, ConversationStore
from ved_backend.push import Notification, PushNotConfiguredError, PushService
from ved_backend.scheduler import ReminderScheduler
from ved_backend.schemas import (
    AcknowledgementEvent,
    AgentReply,
    AgentRequest,
    AgentTurn,
    ClaudeBalanceUpdate,
    ClaudeUsage,
    ConnectionCreate,
    ConnectionList,
    ConnectionPresetList,
    ConnectionPresetSummary,
    ConnectionSummary,
    ConnectionTest,
    ConnectionUpdate,
    ConversationList,
    ConversationStatus,
    ConversationSummary,
    ConversationTranscript,
    DocumentList,
    DocumentSummary,
    FamilyNoteList,
    FamilyNoteSummary,
    FamilyOverview,
    FamilyPersonSummary,
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
    VoiceInfo,
    VoiceSpeakRequest,
    VoiceStatus,
    VoiceTranscript,
)
from ved_backend.token_cipher import TokenCipher
from ved_backend.tools.servers import (
    configured_servers,
    connection_tool_limit_for,
    exposed_tools_for,
)
from ved_backend.tools.toolbox import PLAN, MCPToolbox, RemoteConnection
from ved_backend.turns import TurnItem, TurnRegistry
from ved_backend.uploads import (
    MULTIPART_OVERHEAD_BYTES,
    MalformedUploadError,
    UploadTooLargeError,
)
from ved_backend.usage import UsageStore, money, money_or_none
from ved_backend.users import (
    CurrentUser,
    Speaker,
    UserDirectory,
    is_owner,
    speaker_for,
)
from ved_backend.voice import (
    MAX_AUDIO_BYTES,
    UNAVAILABLE_MESSAGE,
    WAV_MEDIA_TYPE,
    VoiceClient,
    VoiceRejectedError,
    VoiceUnavailableError,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s | %(message)s",
)

logger = logging.getLogger(__name__)

NO_TOOLS_MESSAGE = "No MCP servers are connected, so Ved cannot act yet."
NOTE_NOT_FOUND_MESSAGE = "That family note does not exist."
NOT_NOTE_AUTHOR_MESSAGE = "Only the person who wrote a family note can delete it."
NOT_OWNER_BALANCE_MESSAGE = "Only the owner can change the Claude balance."
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
    cipher = TokenCipher(settings.secret_key) if settings.secret_key else None
    owner_plan = (
        RemoteConnection(
            name=PLAN, url=settings.plan_mcp_url, token=settings.plan_mcp_token
        )
        if settings.plan_configured
        else None
    )
    connections = ConnectionStore(
        session_factory,
        cipher,
        owner_email=settings.owner_email,
        owner_plan=owner_plan,
    )
    toolbox = MCPToolbox(
        configured_servers(settings),
        exposed_tools_for(settings),
        connections=connections.enabled_for,
        connection_tool_limit=connection_tool_limit_for(settings),
    )
    await toolbox.connect()
    usage = UsageStore(session_factory, timezone=settings.timezone)
    provider = build_provider(settings, on_usage=usage.record)

    application.state.toolbox = toolbox
    application.state.usage = usage
    application.state.llm = provider
    application.state.connections = connections
    application.state.users = UserDirectory(session_factory)
    family = build_family_directory(
        settings.family_directory_url, settings.family_directory_token
    )
    application.state.family = family
    application.state.family_notes = FamilyNoteStore(session_factory)
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
    application.state.voice = VoiceClient(settings.voice_url)
    application.state.turns = TurnRegistry()
    application.state.scheduler = scheduler
    application.state.agent = Agent(
        provider,
        toolbox,
        max_tool_rounds=settings.agent_max_tool_rounds,
        timezone=settings.timezone,
        family=family,
    )
    logger.info(
        "Agent ready on %s with %d built-in tools", provider.model, len(toolbox.tools)
    )
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
        await application.state.voice.aclose()
        await family.aclose()
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


async def claude_usage_for(user: User) -> ClaudeUsage:
    usage: UsageStore = app.state.usage
    provider: LLMProvider = app.state.llm
    summary = await usage.summary(datetime.now(UTC))
    return ClaudeUsage(
        provider=settings.llm_provider,
        model=provider.model,
        tracking=settings.llm_provider == ANTHROPIC,
        balance_usd=money_or_none(summary.balance_usd),
        balance_set_at=summary.balance_set_at,
        spent_since_balance_usd=money(summary.spent_since_balance_usd),
        remaining_usd=money_or_none(summary.remaining_usd),
        today_usd=money(summary.today.usd),
        today_messages=summary.today.messages,
        month_usd=money(summary.month_usd),
        last_30_days_usd=money(summary.last_30_days_usd),
        can_edit=is_owner(user),
    )


@app.get("/usage/claude")
async def read_claude_usage(user: CurrentUser) -> ClaudeUsage:
    return await claude_usage_for(user)


@app.put("/usage/claude/balance")
async def set_claude_balance(
    request: ClaudeBalanceUpdate, user: CurrentUser
) -> ClaudeUsage:
    if not is_owner(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=NOT_OWNER_BALANCE_MESSAGE
        )
    usage: UsageStore = app.state.usage
    await usage.set_balance(request.balance_usd, datetime.now(UTC))
    return await claude_usage_for(user)


async def identify_speaker(user: User) -> Speaker:
    family: FamilyDirectory = app.state.family
    person = (await family.current()).person_for_email(user.email)
    if person is not None and not user.name:
        directory: UserDirectory = app.state.users
        await directory.adopt_name(user.id, person.name)
    return speaker_for(user, person)


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
    speaker = await identify_speaker(user)
    try:
        turn = await agent.run(
            request.prompt,
            history,
            user_id=user.id,
            user_line=speaker.line,
            spoken=request.voice,
            reply_language=speaker.language,
        )
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
    user_id: uuid.UUID, speaker: Speaker, request: AgentRequest
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
            agent.stream(
                request.prompt,
                history,
                user_id=user_id,
                user_line=speaker.line,
                spoken=request.voice,
                reply_language=speaker.language,
            )
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
    speaker = await identify_speaker(user)
    items = turns.start(
        user.id,
        conversation_key,
        lambda: stream_turn(user.id, speaker, request),
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


def family_person_summary(person: FamilyPerson) -> FamilyPersonSummary:
    month_day = person.birth_month_day
    return FamilyPersonSummary(
        id=person.id,
        name=person.name,
        aliases=person.aliases,
        relation=person.relation,
        birthday_month=month_day[0] if month_day else None,
        birthday_day=month_day[1] if month_day else None,
        language=person.language,
    )


@app.get("/family")
async def read_family(user: CurrentUser) -> FamilyOverview:
    family = await app.state.family.current()
    me = family.person_for_email(user.email)
    owner = family.owner
    return FamilyOverview(
        people=[family_person_summary(person) for person in family.people],
        me=family_person_summary(me) if me else None,
        owner_name=owner.name if owner else None,
    )


@app.get("/family/notes")
async def list_family_notes(user: CurrentUser) -> FamilyNoteList:
    store: FamilyNoteStore = app.state.family_notes
    entries = await store.recent()
    return FamilyNoteList(
        notes=[
            FamilyNoteSummary(
                id=entry.id,
                text=entry.text,
                author_name=entry.author_name,
                created_at=entry.created_at,
                mine=entry.author_user_id == user.id,
            )
            for entry in entries
        ]
    )


@app.delete("/family/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_family_note(note_id: uuid.UUID, user: CurrentUser) -> None:
    store: FamilyNoteStore = app.state.family_notes
    try:
        await store.delete(user.id, note_id)
    except FamilyNoteNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=NOTE_NOT_FOUND_MESSAGE
        ) from error
    except NotNoteAuthorError as error:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=NOT_NOTE_AUTHOR_MESSAGE
        ) from error


def connection_summary(row: MCPConnection) -> ConnectionSummary:
    return ConnectionSummary(
        id=row.id,
        name=row.name,
        url=row.url,
        enabled=row.enabled,
        has_token=bool(row.token_encrypted),
        created_at=row.created_at,
    )


def connection_store() -> ConnectionStore:
    return app.state.connections


def connection_not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail=str(ConnectionNotFoundError())
    )


def connections_disabled(error: ConnectionsDisabledError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)
    )


@app.get("/connections")
async def list_connections(user: CurrentUser) -> ConnectionList:
    rows = await connection_store().list_for(user.id)
    return ConnectionList(connections=[connection_summary(row) for row in rows])


@app.get("/connections/presets")
async def list_connection_presets(_: CurrentUser) -> ConnectionPresetList:
    return ConnectionPresetList(
        presets=[
            ConnectionPresetSummary(
                id=preset.id,
                label=preset.label,
                name=preset.name,
                url=preset.url,
                help=preset.help,
            )
            for preset in PRESETS
        ]
    )


@app.post("/connections", status_code=status.HTTP_201_CREATED)
async def create_connection(
    request: ConnectionCreate, user: CurrentUser
) -> ConnectionSummary:
    try:
        row = await connection_store().create(
            user.id, request.name, request.url, request.token
        )
    except ConnectionNameTakenError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(error)
        ) from error
    except ConnectionsDisabledError as error:
        raise connections_disabled(error) from error
    return connection_summary(row)


@app.patch("/connections/{connection_id}")
async def update_connection(
    connection_id: uuid.UUID, request: ConnectionUpdate, user: CurrentUser
) -> ConnectionSummary:
    try:
        row = await connection_store().update(
            user.id,
            connection_id,
            enabled=request.enabled,
            url=request.url,
            token=request.token,
        )
    except ConnectionNotFoundError as error:
        raise connection_not_found() from error
    except ConnectionsDisabledError as error:
        raise connections_disabled(error) from error
    return connection_summary(row)


@app.delete("/connections/{connection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_connection(connection_id: uuid.UUID, user: CurrentUser) -> None:
    try:
        await connection_store().delete(user.id, connection_id)
    except ConnectionNotFoundError as error:
        raise connection_not_found() from error


@app.post("/connections/{connection_id}/test")
async def test_connection(
    connection_id: uuid.UUID, user: CurrentUser
) -> ConnectionTest:
    try:
        connection = await connection_store().remote_connection(user.id, connection_id)
    except ConnectionNotFoundError as error:
        raise connection_not_found() from error
    except ConnectionsDisabledError as error:
        raise connections_disabled(error) from error
    report = await probe(connection)
    return ConnectionTest(
        ok=report.ok, tool_count=report.tool_count, error=report.error
    )


@app.exception_handler(VoiceUnavailableError)
async def voice_unavailable(
    _request: Request, _error: VoiceUnavailableError
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"detail": UNAVAILABLE_MESSAGE},
    )


@app.exception_handler(VoiceRejectedError)
async def voice_rejected(_request: Request, error: VoiceRejectedError) -> JSONResponse:
    return JSONResponse(status_code=error.status_code, content={"detail": error.detail})


def voice_client() -> VoiceClient:
    return app.state.voice


@app.get("/voice/status")
async def read_voice_status(_: CurrentUser) -> VoiceStatus:
    return await voice_client().status()


@app.get("/voice/voices")
async def list_voices(_: CurrentUser) -> list[VoiceInfo]:
    return await voice_client().voices()


@app.post("/voice/speak")
async def speak_reply(request: VoiceSpeakRequest, _: CurrentUser) -> StreamingResponse:
    upstream = await voice_client().speak(request.model_dump(exclude_none=True))
    return StreamingResponse(
        upstream.aiter_bytes(),
        media_type=WAV_MEDIA_TYPE,
        background=BackgroundTask(upstream.aclose),
    )


@app.post("/voice/transcribe")
async def transcribe_audio(
    _: CurrentUser,
    audio: Annotated[UploadFile, File()],
    language: Annotated[str | None, Form()] = None,
) -> VoiceTranscript:
    data = await audio.read(MAX_AUDIO_BYTES + 1)
    if len(data) > MAX_AUDIO_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"Audio is larger than {MAX_AUDIO_BYTES // MEBIBYTE} MB.",
        )
    return await voice_client().transcribe(
        data,
        filename=audio.filename or "audio",
        content_type=audio.content_type or "application/octet-stream",
        language=language,
    )
