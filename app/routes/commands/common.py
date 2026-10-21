"""
app/routes/commands/common.py
=============================
Handlers shared by digital and referee mode (newround, status) and the
player-action command set.
"""

import logging
from app.services.room_manager import (
    apply_queued_settings,
    rotate_dealer,
    patch_tracker,
    reset_round_state,
)

log = logging.getLogger(__name__)


# Player-action commands: gated by turn order and bust-vote-pending, and
# trigger the shared after_player_action() follow-up once executed.
PLAYER_ACTION_CMDS = {"hit", "stand", "double", "split"}


def cmd_newround(game_session, parts, *, digital):
    # newround [rotate]
    # Explicit "rotate" arg is still accepted for manual override.
    # In drinking mode the backend auto-decides: rotate when a hard/soft switch
    # fired this round, or when the rotation interval is reached — so the
    # frontend just sends bare "newround" and never makes this call itself.
    explicit_rotate = len(parts) > 1 and parts[1].lower() == "rotate"
    auto_rotate = (
        game_session.drinking_mode and bool(
            game_session.round.switch_this_round in ("hard", "soft") or
            game_session.rounds_this_dealer >= game_session._dealer_rotate_every
        )
    )
    rotate = explicit_rotate or auto_rotate
    # Apply queued settings before the round starts.
    # Capture shoe reference first — if apply_queued_settings creates a fresh
    # Shoe (num_decks change), we must not reshuffle it immediately after.
    shoe_before = game_session.shoe
    setting_changes = apply_queued_settings(game_session)
    for msg in setting_changes:
        log.debug(f"  ⚙️  {msg}")
    if rotate:
        rotate_dealer(game_session)
        game_session.rounds_this_dealer = 1
    else:
        game_session.rounds_this_dealer = game_session.rounds_this_dealer + 1
    reset_round_state(game_session, digital=digital)
    if digital and (game_session.drinking_mode or game_session.shoe.needs_reshuffle()):
        if game_session.shoe is not shoe_before:
            log.debug("  Shoe already fresh from settings change — skipping reshuffle.")
        else:
            game_session.shoe.reset(quiet=True)
            log.debug("  Shoe reshuffled.")
    game_session.start_round()
    patch_tracker(game_session)
    game_session.session.tracker.easy_mode = game_session.easy_mode


def cmd_status(game_session, parts):
    game_session.cmd_status()
