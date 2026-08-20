"""Arena backend package.

The unified server lives in `app.server` (re-exported by `backend.main` for
backward compatibility). This __init__ intentionally avoids eager imports so
`app.server` can import submodules like `backend.websocket_server` without a
circular import.
"""

__all__ = ["app"]


def __getattr__(name: str):
    if name == "app":
        from app.server import app
        return app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
