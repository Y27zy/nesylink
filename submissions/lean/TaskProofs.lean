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

end NesyLink
