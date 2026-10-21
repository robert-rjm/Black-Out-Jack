"""
app/routes/commands/referee.py
==============================
Referee-mode command handlers and the REFEREE_COMMANDS registry.
"""

from engine.referee import RefereeSession
from app.services.game_engine import resolve_endround
from app.routes.commands.common import cmd_newround, cmd_status


def _cmd_referee_deal(game_session, parts):
    game_session.cmd_deal(parts)


def _cmd_referee_action(game_session, parts):
    game_session.cmd_action(parts)


def _cmd_referee_result(game_session, parts):
    game_session.cmd_result(parts)


def _cmd_referee_dealer(game_session, parts):
    game_session.cmd_dealer(parts)


def _cmd_referee_fouraces(game_session, parts):
    game_session.cmd_fouraces(parts)


def _cmd_help_referee(game_session, parts):
    RefereeSession.print_help()


REFEREE_COMMANDS = {
    "deal":     _cmd_referee_deal,
    "action":   _cmd_referee_action,
    "result":   _cmd_referee_result,
    "dealer":   _cmd_referee_dealer,
    "fouraces": _cmd_referee_fouraces,
    "endround": lambda gs, parts: resolve_endround(gs),
    "newround": lambda gs, parts: cmd_newround(gs, parts, digital=False),
    "status":   cmd_status,
    "st":       cmd_status,
    "help":     _cmd_help_referee,
}
