"""
app/services/serializers/admin_afk.py
====================================
admin-AFK vote snapshot helpers, split out of serializer.py.
"""

from app.models.game_room import GameRoom


def _serialize_admin_afk_vote(session: GameRoom, client_id: str) -> dict:
    from app.services.afk import serialize_admin_afk_vote   # afk.py imports this module
    return serialize_admin_afk_vote(session, client_id)
