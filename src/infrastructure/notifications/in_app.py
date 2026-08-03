"""In-app notification "delivery" (ES-355).

Deliberately no adapter class here, unlike ``email.py``: an in-app notification has no
separate send step — persisting a ``Notification`` row via ``NotificationRepository``
*is* the delivery; the frontend reads it back through ``GET /notifications``. See
``application/notifications/alert_owner.py`` for where that persistence happens, and
``infrastructure/persistence/{in_memory,sql}_notifications.py`` for the two backends.
"""
