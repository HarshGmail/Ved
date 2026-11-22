import logging

import httpx2
import pytest
from ved_db import User

from ved_backend.family import (
    CACHE_SECONDS,
    FETCH_TIMEOUT_SECONDS,
    RETRY_AFTER_FAILURE_SECONDS,
    Family,
    FamilyPerson,
    HomeAdminFamilyDirectory,
    NoFamilyDirectory,
    build_family_directory,
    family_block,
)
from ved_backend.users import speaker_for, speaker_label

URL = "http://home-admin.test:3470/api/family"
TOKEN = "s3cret-token"
OWNER_EMAIL = "harsh@example.com"
MOTHER_EMAIL = "amma@example.com"

HARSH = {
    "id": "p1",
    "name": "Harsh",
    "aliases": ["Chinna"],
    "relation": "self",
    "email": "Harsh@Example.com",
    "birthday": "2001-08-16",
    "language": "en",
}
AMMA = {
    "id": "p2",
    "name": "Amma",
    "aliases": ["Mummy", "Mom"],
    "relation": "mother",
    "email": MOTHER_EMAIL,
    "birthday": "--03-03",
    "language": "te",
}
BROTHER = {
    "id": "p3",
    "name": "Ravi",
    "aliases": [],
    "relation": "brother",
    "email": None,
    "birthday": None,
    "language": None,
}
PAYLOAD = {"people": [HARSH, AMMA, BROTHER], "updatedAt": "2026-11-01T00:00:00Z"}


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class Home:
    def __init__(self, *responses) -> None:
        self.responses = list(responses)
        self.requests: list[httpx2.Request] = []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        response = (
            self.responses[0] if len(self.responses) == 1 else self.responses.pop(0)
        )
        if isinstance(response, Exception):
            raise response
        return response


def ok(payload=PAYLOAD) -> httpx2.Response:
    return httpx2.Response(200, json=payload)


def unreachable() -> httpx2.ConnectError:
    return httpx2.ConnectError("connection refused")


def directory_over(home: Home, clock: Clock) -> HomeAdminFamilyDirectory:
    return HomeAdminFamilyDirectory(
        URL, TOKEN, transport=httpx2.MockTransport(home), clock=clock
    )


def names(family: Family) -> list[str]:
    return [person.name for person in family.people]


async def test_the_directory_is_fetched_with_the_bearer_token():
    home = Home(ok())

    family = await directory_over(home, Clock()).current()

    assert names(family) == ["Harsh", "Amma", "Ravi"]
    assert str(home.requests[0].url) == URL
    assert home.requests[0].headers["authorization"] == f"Bearer {TOKEN}"


async def test_requests_use_a_short_timeout():
    directory = directory_over(Home(ok()), Clock())

    assert directory._client.timeout.read == FETCH_TIMEOUT_SECONDS
    assert FETCH_TIMEOUT_SECONDS <= 3.0


async def test_a_fresh_copy_is_served_without_another_request():
    home = Home(ok())
    clock = Clock()
    directory = directory_over(home, clock)

    await directory.current()
    clock.advance(CACHE_SECONDS - 1)
    await directory.current()

    assert len(home.requests) == 1


async def test_the_copy_is_refetched_after_five_minutes():
    changed = {"people": [HARSH]}
    home = Home(ok(), ok(changed))
    clock = Clock()
    directory = directory_over(home, clock)

    await directory.current()
    clock.advance(CACHE_SECONDS)
    family = await directory.current()

    assert len(home.requests) == 2
    assert names(family) == ["Harsh"]


async def test_the_last_good_copy_survives_an_error():
    home = Home(ok(), unreachable())
    clock = Clock()
    directory = directory_over(home, clock)
    await directory.current()

    clock.advance(CACHE_SECONDS)
    family = await directory.current()

    assert names(family) == ["Harsh", "Amma", "Ravi"]


@pytest.mark.parametrize("status_code", [401, 503, 500])
async def test_error_statuses_keep_the_last_good_copy(status_code):
    home = Home(ok(), httpx2.Response(status_code, json={"error": "no"}))
    clock = Clock()
    directory = directory_over(home, clock)
    await directory.current()

    clock.advance(CACHE_SECONDS)

    assert names(await directory.current()) == ["Harsh", "Amma", "Ravi"]


@pytest.mark.parametrize(
    "bad_response",
    [
        httpx2.Response(200, content=b"not json"),
        httpx2.Response(200, json={"people": [{"id": "x"}]}),
        httpx2.Response(200, json={"people": "nobody"}),
    ],
)
async def test_a_malformed_body_keeps_the_last_good_copy(bad_response):
    home = Home(ok(), bad_response)
    clock = Clock()
    directory = directory_over(home, clock)
    await directory.current()

    clock.advance(CACHE_SECONDS)

    assert names(await directory.current()) == ["Harsh", "Amma", "Ravi"]


async def test_a_directory_never_fetched_is_empty_when_the_service_is_down():
    directory = directory_over(Home(unreachable()), Clock())

    family = await directory.current()

    assert family.people == []


async def test_a_failing_service_is_not_asked_again_straight_away():
    home = Home(unreachable(), ok())
    clock = Clock()
    directory = directory_over(home, clock)

    await directory.current()
    clock.advance(RETRY_AFTER_FAILURE_SECONDS - 1)
    assert (await directory.current()).people == []
    assert len(home.requests) == 1

    clock.advance(1)
    assert names(await directory.current()) == ["Harsh", "Amma", "Ravi"]
    assert len(home.requests) == 2


async def test_failures_never_log_the_token_or_emails(caplog):
    home = Home(ok(), httpx2.Response(401, json={"error": TOKEN}))
    clock = Clock()
    directory = directory_over(home, clock)
    await directory.current()
    clock.advance(CACHE_SECONDS)

    with caplog.at_level(logging.DEBUG):
        await directory.current()
        await directory_over(Home(unreachable()), Clock()).current()

    logged = caplog.text
    assert "Family directory unavailable" in logged
    assert TOKEN not in logged
    assert "@" not in logged


async def test_without_a_token_the_directory_is_off_and_empty():
    directory = build_family_directory(URL, "")

    assert isinstance(directory, NoFamilyDirectory)
    assert (await directory.current()).people == []


def test_with_a_token_the_home_admin_directory_is_built():
    assert isinstance(build_family_directory(URL, TOKEN), HomeAdminFamilyDirectory)


def test_the_directory_defaults_to_the_home_admin_container():
    from ved_backend.config import Settings

    settings = Settings(_env_file=None)

    assert settings.family_directory_url == "http://home-admin:3470/api/family"
    assert settings.family_directory_token == ""


def family_of(*people: dict) -> Family:
    return Family.model_validate({"people": list(people)})


def test_a_person_is_found_by_email_ignoring_case():
    family = family_of(HARSH, AMMA)

    assert family.person_for_email("HARSH@example.COM ").name == "Harsh"
    assert family.person_for_email(MOTHER_EMAIL).name == "Amma"
    assert family.person_for_email("stranger@example.com") is None


def test_a_person_without_an_email_is_never_matched():
    family = family_of(BROTHER)

    assert family.person_for_email("") is None


def test_the_owner_is_the_person_related_to_self():
    assert family_of(AMMA, HARSH).owner.name == "Harsh"
    assert family_of(AMMA).owner is None


@pytest.mark.parametrize(
    ("birthday", "expected"),
    [
        ("2001-08-16", (8, 16)),
        ("--08-16", (8, 16)),
        ("--02-29", (2, 29)),
        ("--02-30", None),
        ("--13-01", None),
        ("garbage", None),
        (None, None),
    ],
)
def test_birthdays_parse_with_or_without_a_year(birthday, expected):
    person = FamilyPerson(id="x", name="X", birthday=birthday)

    assert person.birth_month_day == expected


def test_unknown_fields_and_new_languages_do_not_break_parsing():
    person = FamilyPerson.model_validate(
        {"id": "x", "name": " A   B ", "language": "ta", "shoeSize": 9}
    )

    assert person.name == "A B"
    assert person.language == "ta"


def test_a_named_person_is_addressed_with_name_and_relation():
    user = User(email=MOTHER_EMAIL, name=None)
    person = FamilyPerson.model_validate(AMMA)

    assert speaker_label(user, person) == (
        "You are talking with Amma (the owner's mother)."
    )


def test_the_owner_is_described_as_the_owner():
    user = User(email=OWNER_EMAIL, name="Harsh")
    person = FamilyPerson.model_validate(HARSH)

    assert speaker_label(user, person) == "You are talking with Harsh (the owner)."


def test_a_relation_that_is_missing_adds_no_parentheses():
    user = User(email="x@example.com", name=None)
    person = FamilyPerson(id="x", name="Guest", email="x@example.com")

    assert speaker_label(user, person) == "You are talking with Guest."


@pytest.mark.parametrize("stored_name", [None, "Stored Name"])
def test_the_speaker_label_never_contains_an_email(stored_name):
    user = User(email=MOTHER_EMAIL, name=stored_name)
    person = FamilyPerson.model_validate(AMMA)

    assert "@" not in speaker_label(user, person)
    assert "@" not in speaker_label(user)
    assert "example.com" not in speaker_label(user, person)


def test_the_directory_name_wins_over_the_stored_name():
    user = User(email=MOTHER_EMAIL, name="amma.j")
    person = FamilyPerson.model_validate(AMMA)

    assert "amma.j" not in speaker_label(user, person)


def test_the_speaker_carries_the_preferred_language():
    user = User(email=MOTHER_EMAIL, name=None)

    speaker = speaker_for(user, FamilyPerson.model_validate(AMMA))

    assert speaker.language == "te"
    assert speaker_for(user, None).language is None


def test_the_family_block_lists_names_nicknames_relations_and_birthdays():
    block = family_block(family_of(HARSH, AMMA, BROTHER))

    assert block == "\n".join(
        [
            "Family (relations are to Harsh, the owner, "
            "not to the person you are talking with):",
            "- Harsh (also called Chinna), the owner, birthday 16 August",
            "- Amma (also called Mom, Mummy), the owner's mother, birthday 3 March",
            "- Ravi, the owner's brother",
        ]
    )


def test_the_family_block_has_no_emails_or_ids():
    block = family_block(family_of(HARSH, AMMA, BROTHER))

    assert "@" not in block
    assert "example.com" not in block
    for identifier in ("p1", "p2", "p3"):
        assert identifier not in block


def test_the_family_block_does_not_depend_on_directory_order():
    forward = family_block(family_of(HARSH, AMMA, BROTHER))
    shuffled = family_block(family_of(BROTHER, AMMA, HARSH))
    reversed_aliases = family_block(
        family_of(HARSH, {**AMMA, "aliases": ["Mom", "Mummy"]}, BROTHER)
    )

    assert forward == shuffled == reversed_aliases


def test_the_family_block_is_byte_identical_between_calls():
    family = family_of(HARSH, AMMA, BROTHER)

    assert family_block(family) == family_block(family)


def test_a_family_without_an_owner_is_relative_to_the_owner():
    block = family_block(family_of(AMMA))

    assert block.startswith("Family (relations are to the owner,")


def test_an_empty_family_has_no_block():
    assert family_block(Family()) == ""
