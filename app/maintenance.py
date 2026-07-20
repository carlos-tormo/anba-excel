"""Compatibility exports for database maintenance infrastructure.

New code should import from app.db.maintenance or app.db.migrations.
"""

try:
    from .db.maintenance import *  # noqa: F403
except ImportError:  # pragma: no cover
    from db.maintenance import *  # type: ignore  # noqa: F403
