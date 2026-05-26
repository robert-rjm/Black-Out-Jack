# TODO

## Bugs

- [ ] BJ insurance
  - not completing "waiting for others"
  - not launching on splits
- [ ] Player (as dealer) ace of clubs protection against hard dealer switch
- [ ] only admin can give "dealer suggestion" for alternative strategy

### Check

- [ ] Admin God Mode
  - still overpowers all (action vote)
- [ ] check auto insurance
  - only with Aces
- [ ] next round dealing automatically
- [ ] insurance working as intended (group vote)
- [ ] splits
- [ ] UI


## Future
### Features

- [ ] animation for reaching 50 or 100
  - potential extension: give out drinks for when reached
- [ ] insurance BJ: say the potential rule (AJ BJ: insure to risk drink 16 etc.)
- [ ] add win/loss/push % to .csv file
  - also consider adding extra statistics%split, %double
- [ ] Normal mode complete overwork (remove "sip" reference and all other drinking references)
- [ ] beer counter (with approval by admin)

### New Rule Idea

- [ ] every hand from player is `suited` or `21`, then all drink *2 their drinks (excluding BJ Bonus)
- [ ] Dealer wins with 5+ cards, then all drink +2
- [ ] side bets for Dealer to bust
- [ ] Endgame option of "busfahrer"


## Refactor
### app.py

- [ ] **helpers.py** — pure utility functions with no Flask dependency
  - `_generate_room_code()`, `_capture()`, `_classify_rule()`, `_patch_tracker()`, `_NullTracker`
- [ ] **serializers.py** — state serialization
  - `_serialize_card()`, `_serialize_hand()`, `_serialize_state()`
  - `_compute_sip_totals()`, `_compute_dealer_role_sips()`, `_compute_best_play()`
  - `_round_phase()`, `_current_turn()`, `_play_order()`, `_player_done()`, `_hand_done()`
- [ ] **digital.py** — everything for digital mode
  - `_digital_deal_card()`, `_digital_initial_deal()`, `_digital_dealer_turn()`
  - `_deal_pending_split_cards()`, `_digital_get_player_hand()`
  - `_auto_play_npc_turns()`
- [ ] **room.py** — room/client management
  - `_harvest_drink_log()`, `_get_client_info()`, `_is_dealer_client()`, `_newround_rotate()`
- [ ] **app.py (slimmed down)** — Flask routes only
  - All `@app.route` handlers, importing from the above modules
     
### index.html

- [ ] Extract CSS into modular files:
- `static/
  css/
    main.css
    components/
      table.css
      log.css
      controls.css`
- [ ] Extract JS into modular files:
- `static/js/
api.js # fetch wrappers for all /command, /state calls
state.js # polling logic, state diffing
ui/
table.js # render table/cards
log.js # drink log rendering
lobby.js # room creation/join UI
app.js # entry point, wires everything together`
- [ ] Slim down index.html:
