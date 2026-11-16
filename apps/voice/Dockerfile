FROM python:3.13-slim-bookworm AS models

ARG KOKORO_RELEASE=https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0
ARG WHISPER_REPO=https://huggingface.co/Systran/faster-whisper-small/resolve/536b0662742c02347bc0e980a01041f333bce120

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN set -eux; \
    mkdir -p /opt/models/kokoro /opt/models/whisper-small; \
    curl -fsSL --retry 3 -o /opt/models/kokoro/kokoro-v1.0.int8.onnx "$KOKORO_RELEASE/kokoro-v1.0.int8.onnx"; \
    echo "6e742170d309016e5891a994e1ce1559c702a2ccd0075e67ef7157974f6406cb  /opt/models/kokoro/kokoro-v1.0.int8.onnx" | sha256sum -c -; \
    curl -fsSL --retry 3 -o /opt/models/kokoro/voices-v1.0.bin "$KOKORO_RELEASE/voices-v1.0.bin"; \
    echo "bca610b8308e8d99f32e6fe4197e7ec01679264efed0cac9140fe9c29f1fbf7d  /opt/models/kokoro/voices-v1.0.bin" | sha256sum -c -; \
    curl -fsSL --retry 3 -o /opt/models/whisper-small/config.json "$WHISPER_REPO/config.json"; \
    echo "b55496ac7940a7ae47d2c01eab40edfd8701feec1229d9cce3b40014383fb828  /opt/models/whisper-small/config.json" | sha256sum -c -; \
    curl -fsSL --retry 3 -o /opt/models/whisper-small/tokenizer.json "$WHISPER_REPO/tokenizer.json"; \
    echo "fb7b63191e9bb045082c79fd742a3106a12c99513ab30df4a0d47fa6cb6fd0ab  /opt/models/whisper-small/tokenizer.json" | sha256sum -c -; \
    curl -fsSL --retry 3 -o /opt/models/whisper-small/vocabulary.txt "$WHISPER_REPO/vocabulary.txt"; \
    echo "34ce3fe1c5041027b3f8d42912270993f986dbc4bb34cf27f951e34a1e453913  /opt/models/whisper-small/vocabulary.txt" | sha256sum -c -; \
    curl -fsSL --retry 3 -o /opt/models/whisper-small/model.bin "$WHISPER_REPO/model.bin"; \
    echo "3e305921506d8872816023e4c273e75d2419fb89b24da97b4fe7bce14170d671  /opt/models/whisper-small/model.bin" | sha256sum -c -

FROM python:3.13-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    HF_HUB_OFFLINE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-install-project --no-dev

COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

COPY --from=models /opt/models /opt/models

RUN useradd --create-home --uid 1000 ved
USER ved

EXPOSE 8300

CMD ["uvicorn", "ved_voice.server:app", "--host", "0.0.0.0", "--port", "8300"]
