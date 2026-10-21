"""
app/services/serializers/drink_rate.py
=====================================
drink-rate snapshot helpers, split out of serializer.py.
"""

from app.models.game_room import GameRoom


def _serialize_drink_rates(session: GameRoom, client_id: str) -> dict:
    from app.services.drink_rate import serialize_drink_rates   # drink_rate.py imports this module
    return serialize_drink_rates(session, client_id)
