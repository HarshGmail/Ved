import asyncio
import re
import uuid
from dataclasses import dataclass
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from ved_db import MCPConnection, User
from ved_db.models import CONNECTION_NAME_MAX_LENGTH

from ved_backend.token_cipher import TokenCipher
from ved_backend.tools.toolbox import (
    PLAN,
    REMOTE_OPEN_TIMEOUT_SECONDS,
    RemoteConnection,
    is_destructive,
    list_remote_tools,
)

CONNECTION_NAME_MIN_LENGTH = 2
CONNECTION_NAME_PATTERN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
BUILT_IN_PREFIXES = frozenset({"memory", "documents", "web", "people", "reminders"})
ALLOWED_URL_SCHEMES = frozenset({"http", "https"})
URL_MAX_LENGTH = 2048
TOKEN_MAX_LENGTH = 2048


class InvalidConnectionError(ValueError):
    pass


class ConnectionNotFoundError(LookupError):
    pass


class ConnectionNameTakenError(ValueError):
    def __init__(self, name: str) -> None:
        super().__init__(f"You already have a connection named {name!r}")
        self.name = name


class ConnectionsDisabledError(RuntimeError):
    def __init__(self) -> None:
        super().__init__("Connections need VED_SECRET_KEY; run ./ved server or set it")


@dataclass(frozen=True)
class ConnectionPreset:
    id: str
    label: str
    name: str
    url: str
    help: str


PRESETS = (
    ConnectionPreset(
        id="plan",
        label="Plan",
        name=PLAN,
        url="http://family-planner:3456/api/mcp",
        help="Plan → Settings → API tokens",
    ),
    ConnectionPreset(
        id="finances",
        label="MyFinances",
        name="finances",
        url="https://mcp.my-finances.site/mcp",
        help="MyFinances → Integrations → MCP → ingest token",
    ),
)


@dataclass(frozen=True)
class ConnectionProbe:
    ok: bool
    tool_count: int
    error: str | None


def validate_name(name: str) -> str:
    if not (
        CONNECTION_NAME_MIN_LENGTH <= len(name) <= CONNECTION_NAME_MAX_LENGTH
        and CONNECTION_NAME_PATTERN.fullmatch(name)
    ):
        raise InvalidConnectionError(
            "name must be 2 to 20 lowercase letters or digits, with single dashes "
            "between them, such as plan or finances"
        )
    if name in BUILT_IN_PREFIXES:
        raise InvalidConnectionError(f"{name!r} is reserved for Ved's own tools")
    return name


def validate_url(url: str) -> str:
    cleaned = url.strip()
    parts = urlsplit(cleaned)
    if len(cleaned) > URL_MAX_LENGTH or parts.scheme not in ALLOWED_URL_SCHEMES:
        raise InvalidConnectionError("url must be an http:// or https:// address")
    if not parts.netloc:
        raise InvalidConnectionError("url must include a host")
    return cleaned


def validate_token(token: str) -> str:
    if not token.strip() or len(token) > TOKEN_MAX_LENGTH:
        raise InvalidConnectionError("token must be between 1 and 2048 characters")
    return token


def describe_failure(error: BaseException) -> str:
    return str(error) or type(error).__name__


async def probe(connection: RemoteConnection) -> ConnectionProbe:
    try:
        tools = await asyncio.wait_for(
            list_remote_tools(connection), REMOTE_OPEN_TIMEOUT_SECONDS
        )
    except Exception as error:
        return ConnectionProbe(ok=False, tool_count=0, error=describe_failure(error))
    exposed = [tool for tool in tools if not is_destructive(tool.name)]
    return ConnectionProbe(ok=True, tool_count=len(exposed), error=None)


class ConnectionStore:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        cipher: TokenCipher | None,
        *,
        owner_email: str,
        owner_plan: RemoteConnection | None,
    ) -> None:
        self._session_factory = session_factory
        self._cipher = cipher
        self._owner_email = owner_email
        self._owner_plan = owner_plan

    def _require_cipher(self) -> TokenCipher:
        if self._cipher is None:
            raise ConnectionsDisabledError()
        return self._cipher

    async def list_for(self, user_id: uuid.UUID) -> list[MCPConnection]:
        async with self._session_factory() as session:
            rows = await session.scalars(
                select(MCPConnection)
                .where(MCPConnection.user_id == user_id)
                .order_by(MCPConnection.name)
            )
            return list(rows)

    async def create(
        self, user_id: uuid.UUID, name: str, url: str, token: str
    ) -> MCPConnection:
        row = MCPConnection(
            user_id=user_id,
            name=name,
            url=url,
            token_encrypted=self._require_cipher().encrypt(token),
        )
        async with self._session_factory() as session:
            session.add(row)
            try:
                await session.commit()
            except IntegrityError as error:
                await session.rollback()
                raise ConnectionNameTakenError(name) from error
        return row

    async def update(
        self,
        user_id: uuid.UUID,
        connection_id: uuid.UUID,
        *,
        enabled: bool | None,
        url: str | None,
        token: str | None,
    ) -> MCPConnection:
        async with self._session_factory() as session:
            row = await self._owned(session, user_id, connection_id)
            if token is not None:
                row.token_encrypted = self._require_cipher().encrypt(token)
            if url is not None:
                row.url = url
            if enabled is not None:
                row.enabled = enabled
            await session.commit()
        return row

    async def delete(self, user_id: uuid.UUID, connection_id: uuid.UUID) -> None:
        async with self._session_factory() as session:
            row = await self._owned(session, user_id, connection_id)
            await session.delete(row)
            await session.commit()

    async def remote_connection(
        self, user_id: uuid.UUID, connection_id: uuid.UUID
    ) -> RemoteConnection:
        async with self._session_factory() as session:
            row = await self._owned(session, user_id, connection_id)
            return self._decrypted(row)

    async def enabled_for(self, user_id: uuid.UUID) -> list[RemoteConnection]:
        async with self._session_factory() as session:
            rows = await session.scalars(
                select(MCPConnection)
                .where(
                    MCPConnection.user_id == user_id, MCPConnection.enabled.is_(True)
                )
                .order_by(MCPConnection.name)
            )
            connections = [self._decrypted(row) for row in rows] if self._cipher else []
            if self._owner_plan is None or any(
                connection.name == PLAN for connection in connections
            ):
                return connections
            if await self._is_owner(session, user_id):
                connections.append(self._owner_plan)
            return connections

    async def _is_owner(self, session: AsyncSession, user_id: uuid.UUID) -> bool:
        email = await session.scalar(select(User.email).where(User.id == user_id))
        return email == self._owner_email

    def _decrypted(self, row: MCPConnection) -> RemoteConnection:
        return RemoteConnection(
            name=row.name,
            url=row.url,
            token=self._require_cipher().decrypt(row.token_encrypted),
        )

    @staticmethod
    async def _owned(
        session: AsyncSession, user_id: uuid.UUID, connection_id: uuid.UUID
    ) -> MCPConnection:
        row = await session.scalar(
            select(MCPConnection).where(
                MCPConnection.id == connection_id, MCPConnection.user_id == user_id
            )
        )
        if row is None:
            raise ConnectionNotFoundError(str(connection_id))
        return row
