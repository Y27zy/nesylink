import «Strategy»

/-!
  Task-level proof skeleton.

  Concrete task-level subtask composition theorems, with every proof checked
  by Lean.
-/

namespace NesyLink

theorem safe_move_preserves_safe_state
    {s t : State} {a : Action}
    (h : Step s a t)
    (ha : a ∈ [Action.up, Action.down, Action.left, Action.right])
    (hsafe : isSafe s (nextPosition s.player a)) :
    SafeState t := by
  cases h with
  | moveSafe hmove hsafe' =>
      simpa [SafeState] using hsafe'
  | moveBlocked hmove hblocked =>
      exact False.elim (hblocked hsafe)
  | wait =>
      cases ha <;> contradiction
  | shield =>
      cases ha <;> contradiction

def CanOpenChest (s : State) (chest : Position) : Prop :=
  chest ∈ s.chests ∧ adjacent s.player chest

def CanAttackMonster (s : State) (monster : Position) : Prop :=
  monster ∈ s.monsters ∧ adjacent s.player monster

def Task1Done (s : State) : Prop :=
  s.keys > 0 ∧ s.player ∈ s.exits

def Task2Done (s : State) : Prop :=
  s.monsters = [] ∧ s.keys > 0 ∧ s.player ∈ s.exits

def Task3Done (s : State) : Prop :=
  s.monsters = [] ∧ s.keys > 0 ∧ s.player ∈ s.exits

/- Task 1 in controllers/task1.py: get a key first, then leave. -/
inductive Task1Phase where
  | collectKey
  | exit
  | wait
  deriving DecidableEq, Repr

def task1Phase (s : State) : Task1Phase :=
  if s.keys = 0 ∧ s.chests ≠ [] then
    Task1Phase.collectKey
  else if s.keys > 0 ∧ s.exits ≠ [] then
    Task1Phase.exit
  else
    Task1Phase.wait

/- Task 2 in controllers/task2.py: clear the monster before opening the chest. -/
inductive Task2Phase where
  | killMonster
  | collectKey
  | exit
  | wait
  deriving DecidableEq, Repr

def task2Phase (s : State) : Task2Phase :=
  if s.monsters ≠ [] then
    Task2Phase.killMonster
  else if s.keys = 0 ∧ s.chests ≠ [] then
    Task2Phase.collectKey
  else if s.keys > 0 ∧ s.exits ≠ [] then
    Task2Phase.exit
  else
    Task2Phase.wait

/- Task 3 uses the same local priority in every discovered room.  Room-graph
   exploration and exit retrying are represented by `navigate`; the controller
   does not assume a fixed west/east route. -/
inductive Task3Phase where
  | handleMonster
  | openKeyChest
  | waitForKeyUpdate
  | navigate
  deriving DecidableEq, Repr

def ActiveChests (s : State) : List Position :=
  s.chests.filter fun chest => chest ∉ s.openedChests

def task3Phase (s : State) : Task3Phase :=
  if s.monsters ≠ [] then
    Task3Phase.handleMonster
  else if s.keys = 0 ∧ ActiveChests s ≠ [] then
    Task3Phase.openKeyChest
  else if s.keys = 0 then
    Task3Phase.waitForKeyUpdate
  else
    Task3Phase.navigate

theorem task1_collect_key_when_no_key
    (s : State)
    (hKeys : s.keys = 0)
    (hChests : s.chests ≠ []) :
    task1Phase s = Task1Phase.collectKey := by
  unfold task1Phase
  simp [hKeys, hChests]

theorem task1_exit_after_key
    (s : State)
    (hKeys : s.keys > 0)
    (hExits : s.exits ≠ []) :
    task1Phase s = Task1Phase.exit := by
  unfold task1Phase
  have hNotZero : ¬ s.keys = 0 := Nat.ne_of_gt hKeys
  simp [hNotZero, hKeys, hExits]

theorem task2_attack_before_chest
    (s : State)
    (hMonsters : s.monsters ≠ []) :
    task2Phase s = Task2Phase.killMonster := by
  unfold task2Phase
  simp [hMonsters]

theorem task2_collect_key_after_monster
    (s : State)
    (hMonsters : s.monsters = [])
    (hKeys : s.keys = 0)
    (hChests : s.chests ≠ []) :
    task2Phase s = Task2Phase.collectKey := by
  unfold task2Phase
  simp [hMonsters, hKeys, hChests]

theorem task2_exit_after_key
    (s : State)
    (hMonsters : s.monsters = [])
    (hKeys : s.keys > 0)
    (hExits : s.exits ≠ []) :
    task2Phase s = Task2Phase.exit := by
  unfold task2Phase
  have hNotZero : ¬ s.keys = 0 := Nat.ne_of_gt hKeys
  simp [hMonsters, hNotZero, hKeys, hExits]

theorem task3_monster_priority
    (s : State)
    (hMonsters : s.monsters ≠ []) :
    task3Phase s = Task3Phase.handleMonster := by
  unfold task3Phase
  simp [hMonsters]

theorem task3_chest_after_monsters
    (s : State)
    (hMonsters : s.monsters = [])
    (hKeys : s.keys = 0)
    (hChests : ActiveChests s ≠ []) :
    task3Phase s = Task3Phase.openKeyChest := by
  unfold task3Phase
  simp [hMonsters, hKeys, hChests]

theorem task3_waits_for_inventory_update
    (s : State)
    (hMonsters : s.monsters = [])
    (hKeys : s.keys = 0)
    (hChests : ActiveChests s = []) :
    task3Phase s = Task3Phase.waitForKeyUpdate := by
  unfold task3Phase
  simp [hMonsters, hKeys, hChests]

theorem task3_navigates_after_key
    (s : State)
    (hMonsters : s.monsters = [])
    (hKeys : s.keys > 0) :
    task3Phase s = Task3Phase.navigate := by
  unfold task3Phase
  have hNotZero : ¬ s.keys = 0 := Nat.ne_of_gt hKeys
  simp [hMonsters, hNotZero]

theorem task3_cross_exit_budget_positive :
    0 < tileSize := by
  decide

theorem task1_key_then_exit_chain
    (s0 s1 s2 : State)
    (chest exit : Position)
    (_hOpenable : CanOpenChest s0 chest)
    (hOpen : s1 = { s0 with chests := s0.chests.erase chest, keys := s0.keys + 1 })
    (hExit : exit ∈ s1.exits)
    (hMoveExit : s2 = { s1 with player := exit }) :
    Task1Done s2 := by
  unfold Task1Done
  constructor
  · rw [hMoveExit, hOpen]
    simp
  · rw [hMoveExit]
    exact hExit

theorem task2_kill_then_key_then_exit_chain
    (s0 s1 s2 s3 : State)
    (monster chest exit : Position)
    (_hAttackable : CanAttackMonster s0 monster)
    (hKill : s1 = { s0 with monsters := [] })
    (_hOpenable : CanOpenChest s1 chest)
    (hOpen : s2 = { s1 with chests := s1.chests.erase chest, keys := s1.keys + 1 })
    (hExit : exit ∈ s2.exits)
    (hMoveExit : s3 = { s2 with player := exit }) :
    Task2Done s3 := by
  unfold Task2Done
  constructor
  · rw [hMoveExit, hOpen, hKill]
  · constructor
    · rw [hMoveExit, hOpen]
      simp
    · rw [hMoveExit]
      exact hExit

theorem task3_monster_then_chest_then_exit_chain
    (s0 s1 s2 s3 : State)
    (monster chest exit : Position)
    (_hAttackable : CanAttackMonster s0 monster)
    (hKill : s1 = { s0 with monsters := [] })
    (_hOpenable : CanOpenChest s1 chest)
    (hOpen : s2 = {
      s1 with
      chests := s1.chests.erase chest
      openedChests := chest :: s1.openedChests
      keys := s1.keys + 1
    })
    (hExit : exit ∈ s2.exits)
    (hMoveExit : s3 = { s2 with player := exit }) :
    Task3Done s3 := by
  unfold Task3Done
  constructor
  · rw [hMoveExit, hOpen, hKill]
  · constructor
    · rw [hMoveExit, hOpen]
      simp
    · rw [hMoveExit]
      exact hExit

/- Task 4 in controllers/task4.py: local priority is closed chests, then
   sworded monster combat, then switch operation / frontier navigation.
   Bridge reachability is modelled by `isSafe` allowing gaps covered by bridges. -/
inductive Task4Phase where
  | openChest
  | attackGuardian
  | operateSwitch
  | navigate
  deriving DecidableEq, Repr

def task4Phase (s : State) (hasSword : Bool) : Task4Phase :=
  if ActiveChests s ≠ [] then
    Task4Phase.openChest
  else if s.monsters ≠ [] ∧ hasSword then
    Task4Phase.attackGuardian
  else if s.switches ≠ [] then
    Task4Phase.operateSwitch
  else
    Task4Phase.navigate

def Task4Done (s : State) : Prop :=
  s.monsters = [] ∧ s.keys > 0 ∧ s.gold > 0

def CanActivateSwitch (s : State) (sw : Position) : Prop :=
  sw ∈ s.switches ∧ adjacent s.player sw

def BridgeWalkable (s : State) (p : Position) : Prop :=
  p ∈ s.gaps → p ∈ s.bridges

theorem task4_chest_priority
    (s : State)
    (hasSword : Bool)
    (hChests : ActiveChests s ≠ []) :
    task4Phase s hasSword = Task4Phase.openChest := by
  unfold task4Phase
  simp [hChests]

theorem task4_attack_after_chests_with_sword
    (s : State)
    (hChests : ActiveChests s = [])
    (hMonsters : s.monsters ≠ []) :
    task4Phase s true = Task4Phase.attackGuardian := by
  unfold task4Phase
  simp [hChests, hMonsters]

theorem task4_switch_when_no_chest_or_fight
    (s : State)
    (hChests : ActiveChests s = [])
    (hMonsters : s.monsters = [])
    (hSwitches : s.switches ≠ []) :
    task4Phase s false = Task4Phase.operateSwitch := by
  unfold task4Phase
  simp [hChests, hMonsters, hSwitches]

theorem task4_navigate_otherwise
    (s : State)
    (hChests : ActiveChests s = [])
    (hMonsters : s.monsters = [])
    (hSwitches : s.switches = []) :
    task4Phase s false = Task4Phase.navigate := by
  unfold task4Phase
  simp [hChests, hMonsters, hSwitches]

theorem task4_gap_requires_bridge
    (s : State)
    (p : Position)
    (hBridge : p ∈ s.bridges) :
    BridgeWalkable s p := by
  intro _
  exact hBridge

theorem task4_key_sword_kill_chest_chain
    (s0 s1 s2 s3 s4 : State)
    (keyChest swordChest finalChest monster : Position)
    (_hKeyOpenable : CanOpenChest s0 keyChest)
    (hKey : s1 = {
      s0 with
      chests := s0.chests.erase keyChest
      openedChests := keyChest :: s0.openedChests
      keys := s0.keys + 1
    })
    (_hSwordOpenable : CanOpenChest s1 swordChest)
    (hSword : s2 = {
      s1 with
      chests := s1.chests.erase swordChest
      openedChests := swordChest :: s1.openedChests
    })
    (_hAttackable : CanAttackMonster s2 monster)
    (hKill : s3 = { s2 with monsters := [] })
    (_hFinalOpenable : CanOpenChest s3 finalChest)
    (hFinal : s4 = {
      s3 with
      chests := s3.chests.erase finalChest
      openedChests := finalChest :: s3.openedChests
      gold := s3.gold + 1
    }) :
    Task4Done s4 := by
  unfold Task4Done
  constructor
  · rw [hFinal, hKill]
  · constructor
    · rw [hFinal, hKill, hSword, hKey]
      simp
    · rw [hFinal]
      simp

/- Task 5 in controllers/task5.py: press unseen buttons first, then open
   chests (prefer key chests), then frontier / blocked-exit retry, and only
   fight when a monster blocks the local route. -/
inductive Task5Phase where
  | pressButton
  | openChest
  | clearMonster
  | navigate
  deriving DecidableEq, Repr

def UnpressedButtons (s : State) (pressed : List Position) : List Position :=
  s.buttons.filter fun b => b ∉ pressed

def task5Phase
    (s : State)
    (pressed : List Position)
    (monsterBlocks : Bool) :
    Task5Phase :=
  if UnpressedButtons s pressed ≠ [] then
    Task5Phase.pressButton
  else if ActiveChests s ≠ [] ∧ ¬ monsterBlocks then
    Task5Phase.openChest
  else if monsterBlocks ∧ s.monsters ≠ [] then
    Task5Phase.clearMonster
  else
    Task5Phase.navigate

def Task5Done (s : State) : Prop :=
  ActiveChests s = [] ∧ s.keys > 0 ∧ s.gold > 0

def CanPressButton (s : State) (button : Position) : Prop :=
  button ∈ s.buttons ∧ s.player = button

theorem task5_button_priority
    (s : State)
    (pressed : List Position)
    (monsterBlocks : Bool)
    (hButtons : UnpressedButtons s pressed ≠ []) :
    task5Phase s pressed monsterBlocks = Task5Phase.pressButton := by
  unfold task5Phase
  simp [hButtons]

theorem task5_chest_after_buttons
    (s : State)
    (pressed : List Position)
    (hButtons : UnpressedButtons s pressed = [])
    (hChests : ActiveChests s ≠ []) :
    task5Phase s pressed false = Task5Phase.openChest := by
  unfold task5Phase
  simp [hButtons, hChests]

theorem task5_clear_monster_when_blocked
    (s : State)
    (pressed : List Position)
    (hButtons : UnpressedButtons s pressed = [])
    (hChests : ActiveChests s = [])
    (hMonsters : s.monsters ≠ []) :
    task5Phase s pressed true = Task5Phase.clearMonster := by
  unfold task5Phase
  simp [hButtons, hChests, hMonsters]

theorem task5_navigate_when_local_goals_done
    (s : State)
    (pressed : List Position)
    (hButtons : UnpressedButtons s pressed = [])
    (hChests : ActiveChests s = []) :
    task5Phase s pressed false = Task5Phase.navigate := by
  unfold task5Phase
  simp [hButtons, hChests]

theorem task5_button_key_chests_chain
    (s0 s1 s2 s3 s4 : State)
    (button keyChest goldChest healChest westChest : Position)
    (_hPressable : CanPressButton s0 button)
    (_hPress : s1 = { s0 with buttons := s0.buttons.erase button })
    (_hKeyOpenable : CanOpenChest s1 keyChest)
    (hKey : s2 = {
      s1 with
      chests := s1.chests.erase keyChest
      openedChests := keyChest :: s1.openedChests
      keys := s1.keys + 1
    })
    (_hHealOpenable : CanOpenChest s2 healChest)
    (hHeal : s3 = {
      s2 with
      chests := s2.chests.erase healChest
      openedChests := healChest :: s2.openedChests
    })
    (_hGoldOpenable : CanOpenChest s3 goldChest)
    (_hWestOpenable : CanOpenChest s3 westChest)
    (hFinal : s4 = {
      s3 with
      chests := (s3.chests.erase goldChest).erase westChest
      openedChests := westChest :: goldChest :: s3.openedChests
      gold := s3.gold + 2
    })
    (hNoActive : ActiveChests s4 = []) :
    Task5Done s4 := by
  unfold Task5Done
  refine ⟨hNoActive, ?_, ?_⟩
  · rw [hFinal, hHeal, hKey]
    simp
  · rw [hFinal]
    simp

/- Combined Task 3/4/5 subtask composition: each hard task reduces to a finite
   chain of locally justified interactions once vision and planner contracts hold. -/
theorem task345_share_adjacent_interaction
    (s : State)
    (target : Position)
    (hAdj : adjacent s.player target) :
    adjacent s.player target ∧ manhattan s.player target = 1 := by
  exact ⟨hAdj, hAdj⟩

theorem task345_completion_requires_key
    {Done : State → Prop}
    (s : State)
    (hDone : Done s)
    (hImply : Done s → s.keys > 0) :
    s.keys > 0 :=
  hImply hDone

theorem task3_done_implies_key (s : State) (h : Task3Done s) : s.keys > 0 := h.2.1
theorem task4_done_implies_key (s : State) (h : Task4Done s) : s.keys > 0 := h.2.1
theorem task5_done_implies_key (s : State) (h : Task5Done s) : s.keys > 0 := h.2.1

end NesyLink
