import base64
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from py_vapid import Vapid01

BACKEND = Path(__file__).resolve().parents[1]
WEB_CLIENT = BACKEND.parents[1] / "apps" / "web-client"
BACKEND_ENV = BACKEND / ".env"
WEB_ENV = WEB_CLIENT / ".env.local"

PRIVATE_KEY_BYTES = 32


def urlsafe(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def generate() -> tuple[str, str]:
    vapid = Vapid01()
    vapid.generate_keys()
    private_value = vapid.private_key.private_numbers().private_value
    public_point = vapid.public_key.public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    return urlsafe(public_point), urlsafe(
        private_value.to_bytes(PRIVATE_KEY_BYTES, "big")
    )


def upsert(path: Path, values: dict[str, str]) -> None:
    lines = path.read_text().splitlines() if path.exists() else []
    kept = [
        line for line in lines if not any(line.startswith(f"{key}=") for key in values)
    ]
    body = "\n".join([*kept, *(f"{key}={value}" for key, value in values.items())])
    path.write_text(body.rstrip("\n") + "\n")
    print(f"wrote {', '.join(values)} to {path}")


def main() -> None:
    if BACKEND_ENV.exists() and "VED_VAPID_PRIVATE_KEY=" in BACKEND_ENV.read_text():
        print("VAPID keys already present. Delete them first to rotate.")
        print("Rotating invalidates every existing push subscription.")
        sys.exit(1)

    public_key, private_key = generate()
    upsert(
        BACKEND_ENV,
        {"VED_VAPID_PUBLIC_KEY": public_key, "VED_VAPID_PRIVATE_KEY": private_key},
    )
    upsert(WEB_ENV, {"NEXT_PUBLIC_VAPID_PUBLIC_KEY": public_key})
    print("\nBoth files are gitignored. The private key stays on this machine.")


if __name__ == "__main__":
    main()
