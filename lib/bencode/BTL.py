"""bencode.py - `BTL` backwards compatibility support."""

# Compatibility with previous versions:
from lib.bencode.exceptions import BencodeDecodeError as BTFailure  # noqa: F401


__all__ = (
    'BTFailure'
)
