import «Strategy»

/-!
  Task-level proof skeleton.

  Put concrete Task 1-5 subtask composition theorems here. Avoid unexplained
  `sorry`, `admit`, or `axiom` in the final submission.
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
      rcases hsafe' with ⟨hin, hnwall, hntrap, _hnmonster, _hnchest, _hngap⟩
      exact ⟨hin, hnwall, hntrap⟩
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

theorem task1_no_key_go_chest
    (s : State)
    (hKeys : s.keys = 0)
    (hChests : s.chests ≠ []) :
    task1Phase s = Task1Phase.collectKey := by
  unfold task1Phase
  simp [hKeys, hChests]

theorem task1_has_key_go_exit
    (s : State)
    (hKeys : s.keys > 0)
    (hExits : s.exits ≠ []) :
    task1Phase s = Task1Phase.exit := by
  unfold task1Phase
  have hNotZero : ¬ s.keys = 0 := Nat.ne_of_gt hKeys
  simp [hNotZero, hKeys, hExits]

theorem task2_monster_priority
    (s : State)
    (hMonsters : s.monsters ≠ []) :
    task2Phase s = Task2Phase.killMonster := by
  unfold task2Phase
  simp [hMonsters]

theorem task2_after_monster_go_chest
    (s : State)
    (hMonsters : s.monsters = [])
    (hKeys : s.keys = 0)
    (hChests : s.chests ≠ []) :
    task2Phase s = Task2Phase.collectKey := by
  unfold task2Phase
  simp [hMonsters, hKeys, hChests]

theorem task2_has_key_go_exit
    (s : State)
    (hMonsters : s.monsters = [])
    (hKeys : s.keys > 0)
    (hExits : s.exits ≠ []) :
    task2Phase s = Task2Phase.exit := by
  unfold task2Phase
  have hNotZero : ¬ s.keys = 0 := Nat.ne_of_gt hKeys
  simp [hMonsters, hNotZero, hKeys, hExits]

theorem task1_key_door_chain
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

theorem task2_kill_key_exit_chain
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

end NesyLink

