"""Concrete SQL repository implementations.

The pending-action repository lives in ``sql_pending_actions.py``
(``SqlPendingActionRepository``). Re-exported here as the conventional import point;
future aggregates (summaries, users/roles, notifications) add their SQL repositories
alongside it and are re-exported from here.
"""

from src.infrastructure.persistence.sql_pending_actions import SqlPendingActionRepository

__all__ = ["SqlPendingActionRepository"]
