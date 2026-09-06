"""Opaque-looking but decodable cursors, for keyset pagination.

Deliberately base64 of a tiny JSON object rather than an encrypted blob: it
looks opaque enough that participants must treat it as a token to pass back,
but anyone curious can decode it, which is its own lesson about what a cursor
actually is.
"""
import base64
import binascii
import json


class InvalidCursor(ValueError):
    """Raised when a cursor cannot be decoded or does not carry a last_id."""


def encode_cursor(last_id: int) -> str:
    raw = json.dumps({"last_id": last_id}, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor: str) -> int:
    """Return the last_id carried by a cursor, or raise InvalidCursor."""
    if not cursor:
        raise InvalidCursor("Cursor is empty.")
    padded = cursor + "=" * (-len(cursor) % 4)
    try:
        raw = base64.urlsafe_b64decode(padded.encode())
        payload = json.loads(raw)
    except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise InvalidCursor(
            "Cursor is not decodable. Pass back the exact next_cursor value from "
            "the previous response, or omit it to start from the first page."
        ) from exc

    if not isinstance(payload, dict) or "last_id" not in payload:
        raise InvalidCursor("Cursor does not carry a last_id.")

    last_id = payload["last_id"]
    if not isinstance(last_id, int) or isinstance(last_id, bool) or last_id < 0:
        raise InvalidCursor("Cursor last_id must be a non-negative integer.")
    return last_id
