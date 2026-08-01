"""Concrete SQL repository implementations.

The pending-action repository lives in ``sql_pending_actions.py``
(``SqlPendingActionRepository``); shift configuration in ``sql_shift_config.py``
(``SqlShiftConfigRepository``). Re-exported here as the conventional import point;
future aggregates (summaries, users/roles, notifications) add their SQL repositories
alongside them and are re-exported from here.
"""

from src.infrastructure.persistence.sql_pending_actions import SqlPendingActionRepository
from src.infrastructure.persistence.sql_shift_config import SqlShiftConfigRepository

__all__ = ["SqlPendingActionRepository", "SqlShiftConfigRepository"]
