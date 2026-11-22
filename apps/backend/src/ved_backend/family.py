import asyncio
import calendar
import logging
import re
import time
from collections.abc import Callable
from typing import Protocol

import httpx2
from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)

FETCH_TIMEOUT_SECONDS = 3.0
CACHE_SECONDS = 300.0
RETRY_AFTER_FAILURE_SECONDS = 30.0
OWNER_RELATION = "self"
LEAP_YEAR = 2000
BIRTHDAY_PATTERN = re.compile(r"^(?:\d{4}-|--)(\d{2})-(\d{2})$")
MONTH_NAMES = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)
OWNER_PHRASE = "the owner"
FAMILY_HEADING = (
    "Family (relations are to {owner}, not to the person you are talking with):"
)


def collapse_whitespace(value: str) -> str:
    return " ".join(value.split())


class FamilyPerson(BaseModel):
    id: str
    name: str
    aliases: list[str] = Field(default_factory=list)
    relation: str | None = None
    email: str | None = None
    birthday: str | None = None
    language: str | None = None

    @field_validator("name", mode="before")
    @classmethod
    def tidy_name(cls, value: object) -> object:
        return collapse_whitespace(value) if isinstance(value, str) else value

    @field_validator("aliases", mode="before")
    @classmethod
    def tidy_aliases(cls, value: object) -> object:
        if not isinstance(value, list):
            return value
        tidied = (
            collapse_whitespace(alias) for alias in value if isinstance(alias, str)
        )
        return [alias for alias in tidied if alias]

    @field_validator("relation", mode="before")
    @classmethod
    def tidy_relation(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        return collapse_whitespace(value).lower() or None

    @field_validator("email", mode="before")
    @classmethod
    def tidy_email(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        return value.strip().lower() or None

    @field_validator("language", mode="before")
    @classmethod
    def tidy_language(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        return value.strip().lower() or None

    @property
    def is_owner(self) -> bool:
        return self.relation == OWNER_RELATION

    @property
    def birth_month_day(self) -> tuple[int, int] | None:
        match = BIRTHDAY_PATTERN.match(self.birthday or "")
        if match is None:
            return None
        month, day = int(match.group(1)), int(match.group(2))
        if not 1 <= month <= len(MONTH_NAMES):
            return None
        if not 1 <= day <= calendar.monthrange(LEAP_YEAR, month)[1]:
            return None
        return month, day

    @property
    def relation_phrase(self) -> str | None:
        if self.is_owner:
            return OWNER_PHRASE
        if self.relation:
            return f"{OWNER_PHRASE}'s {self.relation}"
        return None


class Family(BaseModel):
    people: list[FamilyPerson] = Field(default_factory=list)

    @property
    def owner(self) -> FamilyPerson | None:
        return next((person for person in self.people if person.is_owner), None)

    def person_for_email(self, email: str) -> FamilyPerson | None:
        wanted = email.strip().lower()
        return next((person for person in self.people if person.email == wanted), None)


EMPTY_FAMILY = Family()


class FamilyDirectory(Protocol):
    async def current(self) -> Family: ...

    async def aclose(self) -> None: ...


class NoFamilyDirectory:
    async def current(self) -> Family:
        return EMPTY_FAMILY

    async def aclose(self) -> None:
        return None


def failure_reason(error: Exception) -> str:
    if isinstance(error, httpx2.HTTPStatusError):
        return f"status {error.response.status_code}"
    return type(error).__name__


class HomeAdminFamilyDirectory:
    def __init__(
        self,
        url: str,
        token: str,
        *,
        transport: httpx2.AsyncBaseTransport | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._url = url
        self._headers = {"Authorization": f"Bearer {token}"}
        self._client = httpx2.AsyncClient(
            timeout=FETCH_TIMEOUT_SECONDS, transport=transport
        )
        self._clock = clock
        self._family = EMPTY_FAMILY
        self._next_attempt_at = 0.0
        self._lock = asyncio.Lock()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def current(self) -> Family:
        if self._clock() < self._next_attempt_at:
            return self._family
        async with self._lock:
            now = self._clock()
            if now < self._next_attempt_at:
                return self._family
            try:
                self._family = await self._fetch()
                self._next_attempt_at = now + CACHE_SECONDS
            except (httpx2.HTTPError, ValueError) as error:
                logger.warning(
                    "Family directory unavailable (%s); keeping the last copy",
                    failure_reason(error),
                )
                self._next_attempt_at = now + RETRY_AFTER_FAILURE_SECONDS
            return self._family

    async def _fetch(self) -> Family:
        response = await self._client.get(self._url, headers=self._headers)
        response.raise_for_status()
        return Family.model_validate(response.json())


def build_family_directory(url: str, token: str) -> FamilyDirectory:
    if not token:
        return NoFamilyDirectory()
    return HomeAdminFamilyDirectory(url, token)


def birthday_phrase(person: FamilyPerson) -> str | None:
    month_day = person.birth_month_day
    if month_day is None:
        return None
    month, day = month_day
    return f"birthday {day} {MONTH_NAMES[month - 1]}"


def family_line(person: FamilyPerson) -> str:
    name = person.name
    if person.aliases:
        nicknames = ", ".join(sorted(person.aliases, key=str.casefold))
        name = f"{name} (also called {nicknames})"
    parts = [name, person.relation_phrase, birthday_phrase(person)]
    return "- " + ", ".join(part for part in parts if part)


def family_block(family: Family) -> str:
    if not family.people:
        return ""
    owner = family.owner
    heading = FAMILY_HEADING.format(
        owner=f"{owner.name}, the owner" if owner else "the owner"
    )
    ordered = sorted(
        family.people,
        key=lambda person: (not person.is_owner, person.name.casefold(), person.id),
    )
    return "\n".join([heading, *(family_line(person) for person in ordered)])
