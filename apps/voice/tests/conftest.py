import pytest
from fastapi.testclient import TestClient

from fakes import FakeRecognizer, FakeSynthesizer, client_for


@pytest.fixture
def synthesizer() -> FakeSynthesizer:
    return FakeSynthesizer()


@pytest.fixture
def recognizer() -> FakeRecognizer:
    return FakeRecognizer()


@pytest.fixture
def client(synthesizer: FakeSynthesizer, recognizer: FakeRecognizer) -> TestClient:
    return client_for(synthesizer, recognizer)
