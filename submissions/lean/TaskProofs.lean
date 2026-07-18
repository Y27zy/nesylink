import «Strategy»

/-!
  Task-level strategy formalization and machine-checked proofs.

  Each completion theorem composes actual `Step` constructors with planner
  subtraces.  The theorem assumptions are the explicit boundary conditions of
  the Python policy: sound perception, a returned route, and an interactable
  target.  No fixed room coordinate or public-map layout is assumed.
-/

namespace NesyLink

/-! ## Generic environment and trace properties -/

theorem safe_implies_walkable
    {s : State} {p : Position}
    (h : isSafe s p) :
    walkable s p := h.1

theorem selected_safe_move_is_environment_step
    {s : State} {a : Action}
    (hMove : actionDirection? a ≠ none)
    (hSafe : isSafe s (nextPosition s.player a)) :
    Step s a (moveResult s a) :=
  Step.moveSafe hMove hSafe

theorem selected_shield_preserves_health (s : State) :
    Step s Action.shield s ∧ s.health = s.health :=
  ⟨Step.shield, rfl⟩

theorem selected_button_press_records_event
    {s : State} {button : Position}
    (hCan : CanPressButton s button) :
    Step s Action.wait (pressButtonResult s button) ∧
    (pressButtonResult s button).buttonsPressed = s.buttonsPressed + 1 := by
  constructor
  · exact Step.pressButton hCan
  · simp [pressButtonResult]

theorem selected_switch_toggles_bridge
    {s : State} {sw : Position}
    (hCan : CanActivateSwitch s sw) :
    Step s Action.attack (activateSwitchResult s sw) ∧
    (activateSwitchResult s sw).bridgeMode = toggleBridge s.bridgeMode := by
  constructor
  · exact Step.activateSwitch hCan
  · simp [activateSwitchResult]

theorem toggle_bridge_changes_mode (mode : BridgeMode) :
    toggleBridge mode ≠ mode := by
  cases mode <;> decide

theorem selected_switch_changes_bridge_mode
    {s : State} {sw : Position}
    (_hCan : CanActivateSwitch s sw) :
    (activateSwitchResult s sw).bridgeMode ≠ s.bridgeMode := by
  simp [activateSwitchResult, toggle_bridge_changes_mode]

theorem uncovered_gap_is_not_safe
    {s : State} {p : Position}
    (hGap : p ∈ s.gaps)
    (hNoBridge : p ∉ activeBridges s) :
    ¬ isSafe s p := by
  intro hSafe
  rcases hSafe.2.2 with hNotGap | hBridge
  · exact hNotGap hGap
  · exact hNoBridge hBridge

theorem active_bridge_covers_hazards
    {s : State} {p : Position}
    (hWalkable : walkable s p)
    (hBridge : p ∈ activeBridges s) :
    isSafe s p :=
  ⟨hWalkable, Or.inr hBridge, Or.inr hBridge⟩

theorem locked_exit_requires_key
    {s : State} {exit : Exit}
    (hKind : exit.kind = ExitKind.lockedKey)
    (hEnabled : exitEnabled s exit) :
    0 < s.keys := by
  simpa [exitEnabled, hKind] using hEnabled

theorem conditional_exit_requires_trigger
    {s : State} {exit : Exit}
    (hKind : exit.kind = ExitKind.conditional)
    (hEnabled : exitEnabled s exit) :
    s.pressedButtons ≠ [] ∨ s.activatedSwitches ≠ [] := by
  simpa [exitEnabled, hKind] using hEnabled

theorem locked_exit_consumes_one_key
    {s : State} {exit : Exit}
    (hKind : exit.kind = ExitKind.lockedKey) :
    (crossExitResult s exit).keys = s.keys - 1 := by
  simp [crossExitResult, hKind]

theorem key_chest_effect
    {s : State} {chest : Chest}
    (hKind : chest.kind = ChestKind.key) :
    (openChestResult s chest).keysCollected = s.keysCollected + 1 ∧
    (openChestResult s chest).keys = s.keys + 1 := by
  simp [openChestResult, hKind, grantChest]

theorem gold_chest_effect
    {s : State} {chest : Chest}
    (hKind : chest.kind = ChestKind.gold) :
    (openChestResult s chest).gold = s.gold + 1 := by
  simp [openChestResult, hKind, grantChest]

theorem sword_chest_effect
    {s : State} {chest : Chest}
    (hKind : chest.kind = ChestKind.sword) :
    (openChestResult s chest).hasSword = true := by
  simp [openChestResult, hKind, grantChest]

private theorem grant_chests_opened_eq (s : State) (kind : ChestKind) :
    (grantChest s kind).chestsOpened = s.chestsOpened := by
  cases kind <;> rfl

private theorem grant_monsters_killed_eq (s : State) (kind : ChestKind) :
    (grantChest s kind).monstersKilled = s.monstersKilled := by
  cases kind <;> rfl

private theorem grant_buttons_pressed_eq (s : State) (kind : ChestKind) :
    (grantChest s kind).buttonsPressed = s.buttonsPressed := by
  cases kind <;> rfl

theorem every_chest_records_progress
    (s : State) (chest : Chest) :
    (openChestResult s chest).chestsOpened = s.chestsOpened + 1 := by
  simp [openChestResult, grant_chests_opened_eq]

theorem killed_monster_records_progress
    (s : State) (monster : Monster) :
    (killMonsterResult s monster).monstersKilled = s.monstersKilled + 1 := by
  simp [killMonsterResult]

theorem crossing_completing_exit_finishes_world
    {s : State} {exit : Exit}
    (hCompletes : exit.completesWorld = true) :
    (crossExitResult s exit).worldCompleted = true := by
  simp [crossExitResult, hCompletes]

theorem opening_victory_chest_finishes_world
    {s : State} {chest : Chest}
    (hCompletes : chest.completesWorld = true) :
    (openChestResult s chest).worldCompleted = true := by
  simp [openChestResult, hCompletes]

private theorem grant_world_remaining_eq (s : State) (kind : ChestKind) :
    (grantChest s kind).worldChestsRemaining = s.worldChestsRemaining := by
  cases kind <;> rfl

theorem opening_last_chest_finishes_world
    {s : State} {chest : Chest}
    (hLast : s.worldChestsRemaining = 1) :
    (openChestResult s chest).worldChestsRemaining = 0 ∧
    (openChestResult s chest).worldCompleted = true := by
  simp [openChestResult, grant_world_remaining_eq, hLast]

theorem exec_one
    {s t : State} {a : Action}
    (h : Step s a t) :
    Exec s [a] t :=
  Exec.cons h Exec.nil

theorem exec_append_step
    {s t u : State} {plan : List Action} {a : Action}
    (hPlan : Exec s plan t)
    (hStep : Step t a u) :
    Exec s (plan ++ [a]) u :=
  exec_append hPlan (exec_one hStep)

private theorem grant_keys_collected_mono (s : State) (kind : ChestKind) :
    s.keysCollected ≤ (grantChest s kind).keysCollected := by
  cases kind <;> simp [grantChest]

private theorem grant_gold_mono (s : State) (kind : ChestKind) :
    s.gold ≤ (grantChest s kind).gold := by
  cases kind <;> simp [grantChest]

private theorem grant_sword_persists
    (s : State) (kind : ChestKind)
    (hSword : s.hasSword = true) :
    (grantChest s kind).hasSword = true := by
  cases kind <;> simp [grantChest, hSword]

private theorem open_chest_keys_mono (s : State) (chest : Chest) :
    s.keysCollected ≤ (openChestResult s chest).keysCollected := by
  simpa [openChestResult] using grant_keys_collected_mono s chest.kind

private theorem open_chest_chests_mono (s : State) (chest : Chest) :
    s.chestsOpened ≤ (openChestResult s chest).chestsOpened := by
  rw [every_chest_records_progress]
  omega

private theorem open_chest_kills_mono (s : State) (chest : Chest) :
    s.monstersKilled ≤ (openChestResult s chest).monstersKilled := by
  simp [openChestResult, grant_monsters_killed_eq]

private theorem open_chest_buttons_mono (s : State) (chest : Chest) :
    s.buttonsPressed ≤ (openChestResult s chest).buttonsPressed := by
  simp [openChestResult, grant_buttons_pressed_eq]

private theorem open_chest_gold_mono (s : State) (chest : Chest) :
    s.gold ≤ (openChestResult s chest).gold := by
  simpa [openChestResult] using grant_gold_mono s chest.kind

private theorem open_chest_sword_persists
    (s : State) (chest : Chest)
    (hSword : s.hasSword = true) :
    (openChestResult s chest).hasSword = true := by
  simpa [openChestResult] using grant_sword_persists s chest.kind hSword

private theorem move_result_keys_eq (s : State) (a : Action) :
    (moveResult s a).keysCollected = s.keysCollected := by
  unfold moveResult
  split <;> rfl

private theorem blocked_result_keys_eq (s : State) (a : Action) :
    (blockedMoveResult s a).keysCollected = s.keysCollected := by
  unfold blockedMoveResult
  split <;> rfl

private theorem move_result_chests_eq (s : State) (a : Action) :
    (moveResult s a).chestsOpened = s.chestsOpened := by
  unfold moveResult
  split <;> rfl

private theorem blocked_result_chests_eq (s : State) (a : Action) :
    (blockedMoveResult s a).chestsOpened = s.chestsOpened := by
  unfold blockedMoveResult
  split <;> rfl

private theorem move_result_kills_eq (s : State) (a : Action) :
    (moveResult s a).monstersKilled = s.monstersKilled := by
  unfold moveResult
  split <;> rfl

private theorem blocked_result_kills_eq (s : State) (a : Action) :
    (blockedMoveResult s a).monstersKilled = s.monstersKilled := by
  unfold blockedMoveResult
  split <;> rfl

private theorem move_result_buttons_eq (s : State) (a : Action) :
    (moveResult s a).buttonsPressed = s.buttonsPressed := by
  unfold moveResult
  split <;> rfl

private theorem blocked_result_buttons_eq (s : State) (a : Action) :
    (blockedMoveResult s a).buttonsPressed = s.buttonsPressed := by
  unfold blockedMoveResult
  split <;> rfl

private theorem move_result_gold_eq (s : State) (a : Action) :
    (moveResult s a).gold = s.gold := by
  unfold moveResult
  split <;> rfl

private theorem blocked_result_gold_eq (s : State) (a : Action) :
    (blockedMoveResult s a).gold = s.gold := by
  unfold blockedMoveResult
  split <;> rfl

private theorem move_result_sword_eq (s : State) (a : Action) :
    (moveResult s a).hasSword = s.hasSword := by
  unfold moveResult
  split <;> rfl

private theorem blocked_result_sword_eq (s : State) (a : Action) :
    (blockedMoveResult s a).hasSword = s.hasSword := by
  unfold blockedMoveResult
  split <;> rfl

theorem step_keys_collected_mono
    {s t : State} {a : Action}
    (h : Step s a t) :
    s.keysCollected ≤ t.keysCollected := by
  cases h with
  | moveSafe => simp [move_result_keys_eq]
  | moveDanger => simp [dangerousMoveResult, move_result_keys_eq]
  | moveBlocked => simp [blocked_result_keys_eq]
  | monsterDamage => simp [monsterDamageResult]
  | attackDamage => simp [damageMonsterResult]
  | attackKill => simp [killMonsterResult]
  | openChest hCan => exact open_chest_keys_mono _ _
  | activateSwitch => simp [activateSwitchResult]
  | attackNoEffect => simp
  | pressButton => simp [pressButtonResult]
  | wait => simp
  | shield => simp
  | crossExit => simp [crossExitResult]

theorem step_chests_opened_mono
    {s t : State} {a : Action}
    (h : Step s a t) :
    s.chestsOpened ≤ t.chestsOpened := by
  cases h with
  | moveSafe => simp [move_result_chests_eq]
  | moveDanger => simp [dangerousMoveResult, move_result_chests_eq]
  | moveBlocked => simp [blocked_result_chests_eq]
  | monsterDamage => simp [monsterDamageResult]
  | attackDamage => simp [damageMonsterResult]
  | attackKill => simp [killMonsterResult]
  | openChest hCan => exact open_chest_chests_mono _ _
  | activateSwitch => simp [activateSwitchResult]
  | attackNoEffect => simp
  | pressButton => simp [pressButtonResult]
  | wait => simp
  | shield => simp
  | crossExit => simp [crossExitResult]

theorem step_monsters_killed_mono
    {s t : State} {a : Action}
    (h : Step s a t) :
    s.monstersKilled ≤ t.monstersKilled := by
  cases h with
  | moveSafe => simp [move_result_kills_eq]
  | moveDanger => simp [dangerousMoveResult, move_result_kills_eq]
  | moveBlocked => simp [blocked_result_kills_eq]
  | monsterDamage => simp [monsterDamageResult]
  | attackDamage => simp [damageMonsterResult]
  | attackKill => simp [killMonsterResult]
  | openChest hCan => exact open_chest_kills_mono _ _
  | activateSwitch => simp [activateSwitchResult]
  | attackNoEffect => simp
  | pressButton => simp [pressButtonResult]
  | wait => simp
  | shield => simp
  | crossExit => simp [crossExitResult]

theorem step_buttons_pressed_mono
    {s t : State} {a : Action}
    (h : Step s a t) :
    s.buttonsPressed ≤ t.buttonsPressed := by
  cases h with
  | moveSafe => simp [move_result_buttons_eq]
  | moveDanger => simp [dangerousMoveResult, move_result_buttons_eq]
  | moveBlocked => simp [blocked_result_buttons_eq]
  | monsterDamage => simp [monsterDamageResult]
  | attackDamage => simp [damageMonsterResult]
  | attackKill => simp [killMonsterResult]
  | openChest hCan => exact open_chest_buttons_mono _ _
  | activateSwitch => simp [activateSwitchResult]
  | attackNoEffect => simp
  | pressButton => simp [pressButtonResult]
  | wait => simp
  | shield => simp
  | crossExit => simp [crossExitResult]

theorem step_gold_mono
    {s t : State} {a : Action}
    (h : Step s a t) :
    s.gold ≤ t.gold := by
  cases h with
  | moveSafe => simp [move_result_gold_eq]
  | moveDanger => simp [dangerousMoveResult, move_result_gold_eq]
  | moveBlocked => simp [blocked_result_gold_eq]
  | monsterDamage => simp [monsterDamageResult]
  | attackDamage => simp [damageMonsterResult]
  | attackKill => simp [killMonsterResult]
  | openChest hCan => exact open_chest_gold_mono _ _
  | activateSwitch => simp [activateSwitchResult]
  | attackNoEffect => simp
  | pressButton => simp [pressButtonResult]
  | wait => simp
  | shield => simp
  | crossExit => simp [crossExitResult]

theorem step_sword_persists
    {s t : State} {a : Action}
    (h : Step s a t)
    (hSword : s.hasSword = true) :
    t.hasSword = true := by
  cases h with
  | moveSafe => simpa [move_result_sword_eq] using hSword
  | moveDanger => simpa [dangerousMoveResult, move_result_sword_eq] using hSword
  | moveBlocked => simpa [blocked_result_sword_eq] using hSword
  | monsterDamage => simpa [monsterDamageResult] using hSword
  | attackDamage => simpa [damageMonsterResult] using hSword
  | attackKill => simpa [killMonsterResult] using hSword
  | openChest hCan => exact open_chest_sword_persists _ _ hSword
  | activateSwitch => simpa [activateSwitchResult] using hSword
  | attackNoEffect => exact hSword
  | pressButton => simpa [pressButtonResult] using hSword
  | wait => exact hSword
  | shield => exact hSword
  | crossExit => simpa [crossExitResult] using hSword

theorem exec_keys_collected_mono
    {s t : State} {plan : List Action}
    (h : Exec s plan t) :
    s.keysCollected ≤ t.keysCollected := by
  induction h with
  | nil => exact Nat.le_refl _
  | cons head tail ih => exact Nat.le_trans (step_keys_collected_mono head) ih

theorem exec_chests_opened_mono
    {s t : State} {plan : List Action}
    (h : Exec s plan t) :
    s.chestsOpened ≤ t.chestsOpened := by
  induction h with
  | nil => exact Nat.le_refl _
  | cons head tail ih => exact Nat.le_trans (step_chests_opened_mono head) ih

theorem exec_monsters_killed_mono
    {s t : State} {plan : List Action}
    (h : Exec s plan t) :
    s.monstersKilled ≤ t.monstersKilled := by
  induction h with
  | nil => exact Nat.le_refl _
  | cons head tail ih => exact Nat.le_trans (step_monsters_killed_mono head) ih

theorem exec_buttons_pressed_mono
    {s t : State} {plan : List Action}
    (h : Exec s plan t) :
    s.buttonsPressed ≤ t.buttonsPressed := by
  induction h with
  | nil => exact Nat.le_refl _
  | cons head tail ih => exact Nat.le_trans (step_buttons_pressed_mono head) ih

theorem exec_gold_mono
    {s t : State} {plan : List Action}
    (h : Exec s plan t) :
    s.gold ≤ t.gold := by
  induction h with
  | nil => exact Nat.le_refl _
  | cons head tail ih => exact Nat.le_trans (step_gold_mono head) ih

theorem exec_sword_persists
    {s t : State} {plan : List Action}
    (h : Exec s plan t)
    (hSword : s.hasSword = true) :
    t.hasSword = true := by
  induction h with
  | nil => exact hSword
  | cons head tail ih => exact ih (step_sword_persists head hSword)

/-! ## Controller phase functions -/

def keyChests (s : State) : List Chest :=
  s.chests.filter fun chest => chest.kind == ChestKind.key

def unpressedButtons (s : State) : List Position :=
  s.buttons.filter fun button => button ∉ s.pressedButtons

inductive Task1Phase where
  | collectKey
  | exit
  | wait
  deriving DecidableEq, Repr

def task1Phase (s : State) : Task1Phase :=
  if s.keys = 0 ∧ s.chests ≠ [] then Task1Phase.collectKey
  else if 0 < s.keys ∧ s.exits ≠ [] then Task1Phase.exit
  else Task1Phase.wait

inductive Task2Phase where
  | killMonster
  | collectKey
  | exit
  | wait
  deriving DecidableEq, Repr

def task2Phase (s : State) : Task2Phase :=
  if s.monsters ≠ [] then Task2Phase.killMonster
  else if s.keys = 0 ∧ s.chests ≠ [] then Task2Phase.collectKey
  else if 0 < s.keys ∧ s.exits ≠ [] then Task2Phase.exit
  else Task2Phase.wait

inductive Task3Phase where
  | handleMonster
  | openKeyChest
  | waitForInventory
  | navigateRoomGraph
  deriving DecidableEq, Repr

def task3Phase (s : State) : Task3Phase :=
  if s.monsters ≠ [] then Task3Phase.handleMonster
  else if s.keys = 0 ∧ s.chests ≠ [] then Task3Phase.openKeyChest
  else if s.keys = 0 ∧ s.openedChests ≠ [] then Task3Phase.waitForInventory
  else Task3Phase.navigateRoomGraph

inductive Task4Phase where
  | openChest
  | attackGuardian
  | inspectBridge
  | operateSwitch
  | navigateRoomGraph
  deriving DecidableEq, Repr

def task4Phase (s : State) (inspectBridge : Bool) : Task4Phase :=
  if s.chests ≠ [] then Task4Phase.openChest
  else if s.monsters ≠ [] ∧ s.hasSword = true then Task4Phase.attackGuardian
  else if inspectBridge then Task4Phase.inspectBridge
  else if s.switches ≠ [] then Task4Phase.operateSwitch
  else Task4Phase.navigateRoomGraph

inductive Task5Phase where
  | guard
  | openKeyChest
  | openChest
  | pressButton
  | explore
  | retry
  deriving DecidableEq, Repr

def task5Phase
    (s : State)
    (danger deferOptional frontierAvailable : Bool) : Task5Phase :=
  if danger then Task5Phase.guard
  else if keyChests s ≠ [] then Task5Phase.openKeyChest
  else if s.chests ≠ [] ∧ ¬ deferOptional then Task5Phase.openChest
  else if unpressedButtons s ≠ [] then Task5Phase.pressButton
  else if frontierAvailable then Task5Phase.explore
  else Task5Phase.retry

theorem task1_collects_before_exit
    (s : State) (hKeys : s.keys = 0) (hChests : s.chests ≠ []) :
    task1Phase s = Task1Phase.collectKey := by
  simp [task1Phase, hKeys, hChests]

theorem task1_exits_after_key
    (s : State) (hKeys : 0 < s.keys) (hExits : s.exits ≠ []) :
    task1Phase s = Task1Phase.exit := by
  have hNotZero : s.keys ≠ 0 := Nat.ne_of_gt hKeys
  simp [task1Phase, hNotZero, hKeys, hExits]

theorem task2_monster_has_priority
    (s : State) (hMonsters : s.monsters ≠ []) :
    task2Phase s = Task2Phase.killMonster := by
  simp [task2Phase, hMonsters]

theorem task2_key_after_monster
    (s : State)
    (hMonsters : s.monsters = [])
    (hKeys : s.keys = 0)
    (hChests : s.chests ≠ []) :
    task2Phase s = Task2Phase.collectKey := by
  simp [task2Phase, hMonsters, hKeys, hChests]

theorem task3_monster_has_priority
    (s : State) (hMonsters : s.monsters ≠ []) :
    task3Phase s = Task3Phase.handleMonster := by
  simp [task3Phase, hMonsters]

theorem task3_navigates_after_inventory_update
    (s : State)
    (hMonsters : s.monsters = [])
    (hKeys : 0 < s.keys) :
    task3Phase s = Task3Phase.navigateRoomGraph := by
  have hNotZero : s.keys ≠ 0 := Nat.ne_of_gt hKeys
  simp [task3Phase, hMonsters, hNotZero]

theorem task4_chest_has_priority
    (s : State) (inspect : Bool) (hChests : s.chests ≠ []) :
    task4Phase s inspect = Task4Phase.openChest := by
  simp [task4Phase, hChests]

theorem task4_attacks_only_with_sword
    (s : State)
    (hChests : s.chests = [])
    (hMonsters : s.monsters ≠ [])
    (hSword : s.hasSword = true) :
    task4Phase s false = Task4Phase.attackGuardian := by
  simp [task4Phase, hChests, hMonsters, hSword]

theorem task4_switch_after_bridge_inspection
    (s : State)
    (hChests : s.chests = [])
    (hNoFight : s.monsters = [] ∨ s.hasSword = false)
    (hSwitches : s.switches ≠ []) :
    task4Phase s false = Task4Phase.operateSwitch := by
  rcases hNoFight with hMonsters | hSword
  · simp [task4Phase, hChests, hMonsters, hSwitches]
  · simp [task4Phase, hChests, hSword, hSwitches]

theorem task5_danger_selects_shield
    (s : State) (defer frontier : Bool) :
    task5Phase s true defer frontier = Task5Phase.guard := by
  simp [task5Phase]

theorem task5_guard_is_allowed_and_preserves_health
    (s : State)
    (hShield : s.hasShield = true) :
    ActionAllowed s Action.shield ∧
    Step s Action.shield s ∧
    s.health = s.health := by
  exact ⟨by simpa [ActionAllowed] using hShield, Step.shield, rfl⟩

theorem task5_key_chest_precedes_optional_targets
    (s : State)
    (hKey : keyChests s ≠ [])
    (defer frontier : Bool) :
    task5Phase s false defer frontier = Task5Phase.openKeyChest := by
  simp [task5Phase, hKey]

theorem task5_button_after_local_chests
    (s : State)
    (hKey : keyChests s = [])
    (hChests : s.chests = [])
    (hButtons : unpressedButtons s ≠ [])
    (frontier : Bool) :
    task5Phase s false false frontier = Task5Phase.pressButton := by
  simp [task5Phase, hKey, hChests, hButtons]

/-! ## Search and policy safety obligations shared by all tasks -/

theorem controller_path_is_safe
    {s : State} {goals : List Position} {path : Path}
    (hBfs : BFSReturns s goals path) :
    ∀ tile, tile ∈ path → isSafe s tile :=
  bfs_return_path_safe hBfs

theorem controller_path_transfers_through_vision
    {observed actual : State} {goals : List Position} {path : Path}
    (hVision : PerceptionContract observed actual)
    (hBfs : BFSReturns observed goals path) :
    ∀ tile, tile ∈ path → isSafe actual tile := by
  intro tile hTile
  exact perceived_safe_is_actually_safe hVision
    (bfs_return_path_safe hBfs tile hTile)

theorem task345_room_search_complete
    {neighbors : RoomNeighbors} {start target : RoomId} {depth : Nat}
    (hReachable : RoomBoundedReachable neighbors start target depth) :
    target ∈ bfsRooms neighbors depth [start] :=
  room_bfs_complete hReachable

/-! ## End-to-end task composition theorems -/

theorem task1_strategy_completes
    {initial nearKey atExit : State}
    {toKey toExit : List Action}
    {keyChest : Chest} {exit : Exit}
    (hToKey : Exec initial toKey nearKey)
    (hKeyKind : keyChest.kind = ChestKind.key)
    (hCanKey : CanOpenChest nearKey keyChest)
    (hToExit : Exec (openChestResult nearKey keyChest) toExit atExit)
    (hCanExit : CanCrossExit atExit exit (directionAction exit.direction))
    (hCompletes : exit.completesWorld = true) :
    TaskCompletable TaskId.task1 initial := by
  have hOpen : Step nearKey Action.attack (openChestResult nearKey keyChest) :=
    Step.openChest hCanKey
  have hPrefix := exec_append_step hToKey hOpen
  have hAtExit := exec_append hPrefix hToExit
  have hCross : Step atExit (directionAction exit.direction)
      (crossExitResult atExit exit) := Step.crossExit hCanExit
  have hAll := exec_append_step hAtExit hCross
  have hKeyAfterOpen := (key_chest_effect (s := nearKey) hKeyKind).1
  have hKeyAtExit := exec_keys_collected_mono hToExit
  have hPositive : 0 < atExit.keysCollected := by omega
  refine ⟨
    ((toKey ++ [Action.attack]) ++ toExit) ++
      [directionAction exit.direction],
    crossExitResult atExit exit,
    hAll,
    ?_
  ⟩
  simp [TaskGoal, crossExitResult, hCompletes, hPositive]

theorem task2_strategy_completes
    {initial nearMonster nearKey atExit : State}
    {toMonster toKey toExit : List Action}
    {monster : Monster} {keyChest : Chest} {exit : Exit}
    (hToMonster : Exec initial toMonster nearMonster)
    (hCanAttack : CanAttackMonster nearMonster monster)
    (hLastHp : monster.hp = 1)
    (hToKey : Exec (killMonsterResult nearMonster monster) toKey nearKey)
    (hKeyKind : keyChest.kind = ChestKind.key)
    (hCanKey : CanOpenChest nearKey keyChest)
    (hToExit : Exec (openChestResult nearKey keyChest) toExit atExit)
    (hCanExit : CanCrossExit atExit exit (directionAction exit.direction))
    (hCompletes : exit.completesWorld = true) :
    TaskCompletable TaskId.task2 initial := by
  have hKill : Step nearMonster Action.attack
      (killMonsterResult nearMonster monster) :=
    Step.attackKill hCanAttack hLastHp
  have hOpen : Step nearKey Action.attack (openChestResult nearKey keyChest) :=
    Step.openChest hCanKey
  have hP1 := exec_append_step hToMonster hKill
  have hP2 := exec_append hP1 hToKey
  have hP3 := exec_append_step hP2 hOpen
  have hP4 := exec_append hP3 hToExit
  have hCross : Step atExit (directionAction exit.direction)
      (crossExitResult atExit exit) := Step.crossExit hCanExit
  have hAll := exec_append_step hP4 hCross
  have hKilledAtKey := exec_monsters_killed_mono hToKey
  have hOpenPreservesKill := step_monsters_killed_mono hOpen
  have hKilledAtExit := exec_monsters_killed_mono hToExit
  have hKeyAtExit := exec_keys_collected_mono hToExit
  have hKillProgress := killed_monster_records_progress nearMonster monster
  have hKeyProgress := (key_chest_effect (s := nearKey) hKeyKind).1
  have hKilledPositive : 0 < atExit.monstersKilled := by omega
  have hKeyPositive : 0 < atExit.keysCollected := by omega
  refine ⟨
    ((((toMonster ++ [Action.attack]) ++ toKey) ++ [Action.attack]) ++ toExit) ++
      [directionAction exit.direction],
    crossExitResult atExit exit,
    hAll,
    ?_
  ⟩
  simp [TaskGoal, crossExitResult, hCompletes, hKilledPositive, hKeyPositive]

theorem task3_strategy_completes
    {initial nearMonster nearKey atExit : State}
    {toMonster toKey toExit : List Action}
    {monster : Monster} {keyChest : Chest} {exit : Exit}
    (hToMonster : Exec initial toMonster nearMonster)
    (hCanAttack : CanAttackMonster nearMonster monster)
    (hLastHp : monster.hp = 1)
    (hToKey : Exec (killMonsterResult nearMonster monster) toKey nearKey)
    (hKeyKind : keyChest.kind = ChestKind.key)
    (hCanKey : CanOpenChest nearKey keyChest)
    (hToExit : Exec (openChestResult nearKey keyChest) toExit atExit)
    (hVisited : 1 ≤ atExit.visitedRooms.length)
    (hCanExit : CanCrossExit atExit exit (directionAction exit.direction))
    (hCompletes : exit.completesWorld = true) :
    TaskCompletable TaskId.task3 initial := by
  have hKill : Step nearMonster Action.attack
      (killMonsterResult nearMonster monster) :=
    Step.attackKill hCanAttack hLastHp
  have hOpen : Step nearKey Action.attack (openChestResult nearKey keyChest) :=
    Step.openChest hCanKey
  have hP1 := exec_append_step hToMonster hKill
  have hP2 := exec_append hP1 hToKey
  have hP3 := exec_append_step hP2 hOpen
  have hP4 := exec_append hP3 hToExit
  have hCross : Step atExit (directionAction exit.direction)
      (crossExitResult atExit exit) := Step.crossExit hCanExit
  have hAll := exec_append_step hP4 hCross
  have hKillProgress := killed_monster_records_progress nearMonster monster
  have hKilledAtKey := exec_monsters_killed_mono hToKey
  have hOpenPreservesKill := step_monsters_killed_mono hOpen
  have hKilledAtExit := exec_monsters_killed_mono hToExit
  have hKeyProgress := (key_chest_effect (s := nearKey) hKeyKind).1
  have hKeyAtExit := exec_keys_collected_mono hToExit
  have hKilledPositive : 0 < atExit.monstersKilled := by omega
  have hKeyPositive : 0 < atExit.keysCollected := by omega
  have hVisitedFinal : 2 ≤ (crossExitResult atExit exit).visitedRooms.length := by
    change 2 ≤ Nat.succ atExit.visitedRooms.length
    omega
  refine ⟨
    ((((toMonster ++ [Action.attack]) ++ toKey) ++ [Action.attack]) ++ toExit) ++
      [directionAction exit.direction],
    crossExitResult atExit exit,
    hAll,
    ?_
  ⟩
  refine ⟨?_, ?_, ?_, hVisitedFinal⟩
  · simp [crossExitResult, hCompletes]
  · simpa [crossExitResult] using hKilledPositive
  · simpa [crossExitResult] using hKeyPositive

theorem task4_strategy_completes
    {initial nearSwitch nearKey nearSword nearMonster nearGold : State}
    {toSwitch toKey toSword toMonster toGold : List Action}
    {switch : Position}
    {keyChest swordChest goldChest : Chest}
    {monster : Monster}
    (hToSwitch : Exec initial toSwitch nearSwitch)
    (hCanSwitch : CanActivateSwitch nearSwitch switch)
    (hToKey : Exec (activateSwitchResult nearSwitch switch) toKey nearKey)
    (hKeyKind : keyChest.kind = ChestKind.key)
    (hCanKey : CanOpenChest nearKey keyChest)
    (hToSword : Exec (openChestResult nearKey keyChest) toSword nearSword)
    (hSwordKind : swordChest.kind = ChestKind.sword)
    (hCanSword : CanOpenChest nearSword swordChest)
    (hToMonster : Exec (openChestResult nearSword swordChest) toMonster nearMonster)
    (hCanAttack : CanAttackMonster nearMonster monster)
    (hLastHp : monster.hp = 1)
    (hToGold : Exec (killMonsterResult nearMonster monster) toGold nearGold)
    (hGoldKind : goldChest.kind = ChestKind.gold)
    (hCanGold : CanOpenChest nearGold goldChest)
    (hCompletes : goldChest.completesWorld = true) :
    TaskCompletable TaskId.task4 initial := by
  have hSwitch : Step nearSwitch Action.attack
      (activateSwitchResult nearSwitch switch) :=
    Step.activateSwitch hCanSwitch
  have hOpenKey : Step nearKey Action.attack (openChestResult nearKey keyChest) :=
    Step.openChest hCanKey
  have hOpenSword : Step nearSword Action.attack
      (openChestResult nearSword swordChest) := Step.openChest hCanSword
  have hKill : Step nearMonster Action.attack
      (killMonsterResult nearMonster monster) :=
    Step.attackKill hCanAttack hLastHp
  have hOpenGold : Step nearGold Action.attack
      (openChestResult nearGold goldChest) := Step.openChest hCanGold
  have hP0 := exec_append_step hToSwitch hSwitch
  have hP1 := exec_append hP0 hToKey
  have hP2 := exec_append_step hP1 hOpenKey
  have hP3 := exec_append hP2 hToSword
  have hP4 := exec_append_step hP3 hOpenSword
  have hP5 := exec_append hP4 hToMonster
  have hP6 := exec_append_step hP5 hKill
  have hP7 := exec_append hP6 hToGold
  have hP8 := exec_append_step hP7 hOpenGold
  have hKeyProgress := (key_chest_effect (s := nearKey) hKeyKind).1
  have hKeySword := exec_keys_collected_mono hToSword
  have hOpenSwordKey := step_keys_collected_mono hOpenSword
  have hKeyMonster := exec_keys_collected_mono hToMonster
  have hKillKey := step_keys_collected_mono hKill
  have hKeyGold := exec_keys_collected_mono hToGold
  have hOpenGoldKey := step_keys_collected_mono hOpenGold
  have hSwordProgress := sword_chest_effect (s := nearSword) hSwordKind
  have hSwordMonster := exec_sword_persists hToMonster hSwordProgress
  have hSwordGoldStart := step_sword_persists hKill hSwordMonster
  have hSwordGold := exec_sword_persists hToGold hSwordGoldStart
  have hSwordFinal := step_sword_persists hOpenGold hSwordGold
  have hKillProgress := killed_monster_records_progress nearMonster monster
  have hKillGold := exec_monsters_killed_mono hToGold
  have hOpenGoldKill := step_monsters_killed_mono hOpenGold
  have hGoldProgress := gold_chest_effect (s := nearGold) hGoldKind
  have hWorld := opening_victory_chest_finishes_world
    (s := nearGold) (chest := goldChest) hCompletes
  have hKeyPositive :
      0 < (openChestResult nearGold goldChest).keysCollected := by omega
  have hKillPositive :
      0 < (openChestResult nearGold goldChest).monstersKilled := by omega
  have hGoldPositive : 0 < (openChestResult nearGold goldChest).gold := by omega
  refine ⟨
    _,
    openChestResult nearGold goldChest,
    hP8,
    hWorld,
    hKeyPositive,
    hSwordFinal,
    hKillPositive,
    hGoldPositive
  ⟩

theorem task5_strategy_completes
    {initial nearKey nearGold : State}
    {toKey toGold : List Action}
    {button : Position} {keyChest goldChest : Chest}
    (hCanButton : CanPressButton initial button)
    (hToKey : Exec (pressButtonResult initial button) toKey nearKey)
    (hKeyKind : keyChest.kind = ChestKind.key)
    (hCanKey : CanOpenChest nearKey keyChest)
    (hToGold : Exec (openChestResult nearKey keyChest) toGold nearGold)
    (hGoldKind : goldChest.kind = ChestKind.gold)
    (hCanGold : CanOpenChest nearGold goldChest)
    (hLastChest : nearGold.worldChestsRemaining = 1) :
    TaskCompletable TaskId.task5 initial := by
  have hButton : Step initial Action.wait (pressButtonResult initial button) :=
    Step.pressButton hCanButton
  have hOpenKey : Step nearKey Action.attack (openChestResult nearKey keyChest) :=
    Step.openChest hCanKey
  have hOpenGold : Step nearGold Action.attack
      (openChestResult nearGold goldChest) := Step.openChest hCanGold
  have hP0 := exec_one hButton
  have hP1 := exec_append hP0 hToKey
  have hP2 := exec_append_step hP1 hOpenKey
  have hP3 := exec_append hP2 hToGold
  have hP4 := exec_append_step hP3 hOpenGold
  have hButtonProgress := (selected_button_press_records_event hCanButton).2
  have hButtonsKey := exec_buttons_pressed_mono hToKey
  have hOpenKeyButtons := step_buttons_pressed_mono hOpenKey
  have hButtonsGold := exec_buttons_pressed_mono hToGold
  have hOpenGoldButtons := step_buttons_pressed_mono hOpenGold
  have hKeyProgress := (key_chest_effect (s := nearKey) hKeyKind).1
  have hKeyGold := exec_keys_collected_mono hToGold
  have hOpenGoldKey := step_keys_collected_mono hOpenGold
  have hGoldProgress := gold_chest_effect (s := nearGold) hGoldKind
  have hChestProgress := every_chest_records_progress nearKey keyChest
  have hChestGold := exec_chests_opened_mono hToGold
  have hChestAfterGold := every_chest_records_progress nearGold goldChest
  have hLastResult := opening_last_chest_finishes_world
    (s := nearGold) (chest := goldChest) hLastChest
  have hButtonPositive :
      0 < (openChestResult nearGold goldChest).buttonsPressed := by omega
  have hKeyPositive :
      0 < (openChestResult nearGold goldChest).keysCollected := by omega
  have hGoldPositive : 0 < (openChestResult nearGold goldChest).gold := by omega
  have hChestPositive :
      0 < (openChestResult nearGold goldChest).chestsOpened := by omega
  refine ⟨
    _,
    openChestResult nearGold goldChest,
    hP4,
    hLastResult.2,
    hLastResult.1,
    hChestPositive,
    hKeyPositive,
    hGoldPositive,
    hButtonPositive
  ⟩

end NesyLink
