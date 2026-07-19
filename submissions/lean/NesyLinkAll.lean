/-!
  Standalone compilation unit for the complete NesyLink formalization.

  This file concatenates Environment.lean, Strategy.lean, and TaskProofs.lean
  in dependency order and intentionally has no local imports. The three
  modular source files are retained for readability and maintenance.
-/

/-!
  Symbolic environment for the five NesyLink mathematical-logic tasks.

  The Python policy receives pixels and constructs `SymbolicState`; this file
  starts at that verified boundary.  It models the object attributes and game
  transitions used by `vision.py`, `state.py`, `planner.py`, and the five task
  controllers.  Pixel-classifier correctness is stated separately as a
  perception contract in `Strategy.lean`.
-/

namespace NesyLink

abbrev Position := Nat × Nat
abbrev RoomId := Nat

inductive Direction where
  | north
  | south
  | west
  | east
  deriving DecidableEq, Repr

inductive Action where
  | wait
  | up
  | down
  | left
  | right
  | attack
  | shield
  deriving DecidableEq, Repr

inductive ChestKind where
  | key
  | gold
  | heal
  | sword
  | shield
  | item
  deriving DecidableEq, Repr

inductive ExitKind where
  | normal
  | lockedKey
  | conditional
  deriving DecidableEq, Repr

inductive MonsterKind where
  | chaser
  | patroller
  | ambusher
  deriving DecidableEq, Repr

inductive BridgeMode where
  | horizontal
  | vertical
  deriving DecidableEq, Repr

inductive TaskId where
  | task1
  | task2
  | task3
  | task4
  | task5
  deriving DecidableEq, Repr

structure Chest where
  pos : Position
  kind : ChestKind
  completesWorld : Bool
  deriving DecidableEq, Repr

structure Monster where
  pos : Position
  kind : MonsterKind
  hp : Nat
  deriving DecidableEq, Repr

structure Exit where
  pos : Position
  direction : Direction
  targetRoom : RoomId
  arrival : Position
  kind : ExitKind
  completesWorld : Bool
  deriving DecidableEq, Repr

structure State where
  room : RoomId
  player : Position
  facing : Direction
  health : Nat
  maxHealth : Nat
  keys : Nat
  gold : Nat
  hasSword : Bool
  hasShield : Bool
  walls : List Position
  traps : List Position
  gaps : List Position
  npcs : List Position
  chests : List Chest
  openedChests : List Chest
  exits : List Exit
  monsters : List Monster
  buttons : List Position
  pressedButtons : List Position
  switches : List Position
  activatedSwitches : List Position
  bridgeHorizontal : List Position
  bridgeVertical : List Position
  bridgeMode : BridgeMode
  visitedRooms : List RoomId
  keysCollected : Nat
  chestsOpened : Nat
  monstersKilled : Nat
  buttonsPressed : Nat
  itemsCollected : Nat
  worldChestsRemaining : Nat
  worldCompleted : Bool
  deriving DecidableEq, Repr

def roomWidth : Nat := 10
def roomHeight : Nat := 8
def tileSize : Nat := 16

def inBounds (p : Position) : Prop :=
  p.1 < roomWidth ∧ p.2 < roomHeight

def manhattan (a b : Position) : Nat :=
  let dx := if a.1 ≤ b.1 then b.1 - a.1 else a.1 - b.1
  let dy := if a.2 ≤ b.2 then b.2 - a.2 else a.2 - b.2
  dx + dy

def adjacent (a b : Position) : Prop :=
  manhattan a b = 1

def directionAction : Direction → Action
  | Direction.north => Action.up
  | Direction.south => Action.down
  | Direction.west => Action.left
  | Direction.east => Action.right

def actionDirection? : Action → Option Direction
  | Action.up => some Direction.north
  | Action.down => some Direction.south
  | Action.left => some Direction.west
  | Action.right => some Direction.east
  | _ => none

def nextPosition (p : Position) : Action → Position
  | Action.up => (p.1, p.2 - 1)
  | Action.down => (p.1, p.2 + 1)
  | Action.left => (p.1 - 1, p.2)
  | Action.right => (p.1 + 1, p.2)
  | _ => p

def facingPosition (p : Position) : Direction → Position
  | Direction.north => (p.1, p.2 - 1)
  | Direction.south => (p.1, p.2 + 1)
  | Direction.west => (p.1 - 1, p.2)
  | Direction.east => (p.1 + 1, p.2)

def faces (s : State) (p : Position) : Prop :=
  facingPosition s.player s.facing = p

def chestPositions (s : State) : List Position :=
  s.chests.map Chest.pos

def openedChestPositions (s : State) : List Position :=
  s.openedChests.map Chest.pos

def monsterPositions (s : State) : List Position :=
  s.monsters.map Monster.pos

def activeBridges (s : State) : List Position :=
  match s.bridgeMode with
  | BridgeMode.horizontal => s.bridgeHorizontal
  | BridgeMode.vertical => s.bridgeVertical

/- `walkable` describes engine collision. Traps and uncovered gaps are
   walkable-but-dangerous and are excluded by the stronger `isSafe` predicate. -/
def walkable (s : State) (p : Position) : Prop :=
  inBounds p ∧
  p ∉ s.walls ∧
  p ∉ monsterPositions s ∧
  p ∉ chestPositions s ∧
  p ∉ openedChestPositions s ∧
  p ∉ s.npcs

def isSafe (s : State) (p : Position) : Prop :=
  walkable s p ∧
  (p ∉ s.traps ∨ p ∈ activeBridges s) ∧
  (p ∉ s.gaps ∨ p ∈ activeBridges s)

def onHazard (s : State) (p : Position) : Prop :=
  (p ∈ s.traps ∧ p ∉ activeBridges s) ∨
  (p ∈ s.gaps ∧ p ∉ activeBridges s)

def threatened (s : State) : Prop :=
  ∃ monster, monster ∈ s.monsters ∧ adjacent s.player monster.pos

def SafeState (s : State) : Prop :=
  0 < s.health ∧ isSafe s s.player

def WellFormed (s : State) : Prop :=
  inBounds s.player ∧
  s.health ≤ s.maxHealth ∧
  (∀ p, p ∈ s.walls → inBounds p) ∧
  (∀ c, c ∈ s.chests → inBounds c.pos) ∧
  (∀ m, m ∈ s.monsters → inBounds m.pos ∧ 0 < m.hp) ∧
  (∀ e, e ∈ s.exits → inBounds e.pos ∧ inBounds e.arrival)

def CanOpenChest (s : State) (c : Chest) : Prop :=
  c ∈ s.chests ∧ faces s c.pos

def CanAttackMonster (s : State) (m : Monster) : Prop :=
  s.hasSword = true ∧ m ∈ s.monsters ∧ faces s m.pos

def CanActivateSwitch (s : State) (sw : Position) : Prop :=
  sw ∈ s.switches ∧ faces s sw

def CanPressButton (s : State) (button : Position) : Prop :=
  button ∈ s.buttons ∧ button ∉ s.pressedButtons ∧ s.player = button

def exitEnabled (s : State) (e : Exit) : Prop :=
  match e.kind with
  | ExitKind.normal => True
  | ExitKind.lockedKey => 0 < s.keys
  | ExitKind.conditional => s.pressedButtons ≠ [] ∨ s.activatedSwitches ≠ []

def CanCrossExit (s : State) (e : Exit) (a : Action) : Prop :=
  e ∈ s.exits ∧
  s.player = e.pos ∧
  directionAction e.direction = a ∧
  exitEnabled s e

def grantChest (s : State) : ChestKind → State
  | ChestKind.key => {
      s with
      keys := s.keys + 1
      keysCollected := s.keysCollected + 1
    }
  | ChestKind.gold => { s with gold := s.gold + 1 }
  | ChestKind.heal => {
      s with health := min s.maxHealth (s.health + 2)
    }
  | ChestKind.sword => {
      s with
      hasSword := true
      itemsCollected := s.itemsCollected + 1
    }
  | ChestKind.shield => {
      s with
      hasShield := true
      itemsCollected := s.itemsCollected + 1
    }
  | ChestKind.item => {
      s with itemsCollected := s.itemsCollected + 1
    }

def openChestResult (s : State) (c : Chest) : State :=
  let granted := grantChest s c.kind
  {
    granted with
    chests := granted.chests.erase c
    openedChests := c :: granted.openedChests
    chestsOpened := granted.chestsOpened + 1
    worldChestsRemaining := granted.worldChestsRemaining - 1
    worldCompleted :=
      granted.worldCompleted ||
      c.completesWorld ||
      (granted.worldChestsRemaining == 1)
  }

def damageMonsterResult (s : State) (m : Monster) : State :=
  let damaged := { m with hp := m.hp - 1 }
  { s with monsters := damaged :: s.monsters.erase m }

def killMonsterResult (s : State) (m : Monster) : State :=
  {
    s with
    monsters := s.monsters.erase m
    monstersKilled := s.monstersKilled + 1
  }

def pressButtonResult (s : State) (button : Position) : State :=
  {
    s with
    pressedButtons := button :: s.pressedButtons
    buttonsPressed := s.buttonsPressed + 1
  }

def toggleBridge : BridgeMode → BridgeMode
  | BridgeMode.horizontal => BridgeMode.vertical
  | BridgeMode.vertical => BridgeMode.horizontal

def activateSwitchResult (s : State) (sw : Position) : State :=
  {
    s with
    bridgeMode := toggleBridge s.bridgeMode
    activatedSwitches := sw :: s.activatedSwitches
  }

def moveResult (s : State) (a : Action) : State :=
  match actionDirection? a with
  | some direction => {
      s with
      player := nextPosition s.player a
      facing := direction
    }
  | none => s

def blockedMoveResult (s : State) (a : Action) : State :=
  match actionDirection? a with
  | some direction => { s with facing := direction }
  | none => s

def dangerousMoveResult (s : State) (a : Action) : State :=
  { moveResult s a with health := s.health - 1 }

def monsterDamageResult (s : State) : State :=
  { s with health := s.health - 1 }

def crossExitResult (s : State) (e : Exit) : State :=
  {
    s with
    room := e.targetRoom
    player := e.arrival
    facing := e.direction
    keys := match e.kind with
      | ExitKind.lockedKey => s.keys - 1
      | _ => s.keys
    visitedRooms := e.targetRoom :: s.visitedRooms
    worldCompleted := s.worldCompleted || e.completesWorld
  }

def noInteractionAhead (s : State) : Prop :=
  (∀ m, m ∈ s.monsters → ¬ faces s m.pos) ∧
  (∀ c, c ∈ s.chests → ¬ faces s c.pos) ∧
  (∀ sw, sw ∈ s.switches → ¬ faces s sw)

/- Relational engine semantics.  The controller proves properties of the
   constructors it intentionally selects; unsafe transitions remain present so
   the environment model does not silently identify "unsafe" with "impossible". -/
inductive Step : State → Action → State → Prop where
  | moveSafe
      {s : State} {a : Action}
      (hMove : actionDirection? a ≠ none)
      (hSafe : isSafe s (nextPosition s.player a)) :
      Step s a (moveResult s a)
  | moveDanger
      {s : State} {a : Action}
      (hMove : actionDirection? a ≠ none)
      (hWalkable : walkable s (nextPosition s.player a))
      (hDanger : onHazard s (nextPosition s.player a))
      (hAlive : 0 < s.health) :
      Step s a (dangerousMoveResult s a)
  | moveBlocked
      {s : State} {a : Action}
      (hMove : actionDirection? a ≠ none)
      (hBlocked : ¬ walkable s (nextPosition s.player a))
      (hNoExit : ∀ e, ¬ CanCrossExit s e a) :
      Step s a (blockedMoveResult s a)
  | monsterDamage
      {s : State}
      (hThreat : threatened s)
      (hAlive : 0 < s.health) :
      Step s Action.wait (monsterDamageResult s)
  | attackDamage
      {s : State} {m : Monster}
      (hCan : CanAttackMonster s m)
      (hHp : 1 < m.hp) :
      Step s Action.attack (damageMonsterResult s m)
  | attackKill
      {s : State} {m : Monster}
      (hCan : CanAttackMonster s m)
      (hHp : m.hp = 1) :
      Step s Action.attack (killMonsterResult s m)
  | openChest
      {s : State} {c : Chest}
      (hCan : CanOpenChest s c) :
      Step s Action.attack (openChestResult s c)
  | activateSwitch
      {s : State} {sw : Position}
      (hCan : CanActivateSwitch s sw) :
      Step s Action.attack (activateSwitchResult s sw)
  | attackNoEffect
      {s : State}
      (hNone : noInteractionAhead s) :
      Step s Action.attack s
  | pressButton
      {s : State} {button : Position}
      (hCan : CanPressButton s button) :
      Step s Action.wait (pressButtonResult s button)
  | wait
      {s : State} :
      Step s Action.wait s
  | shield
      {s : State} :
      Step s Action.shield s
  | crossExit
      {s : State} {e : Exit} {a : Action}
      (hCan : CanCrossExit s e a) :
      Step s a (crossExitResult s e)

inductive Exec : State → List Action → State → Prop where
  | nil {s : State} : Exec s [] s
  | cons
      {s t u : State} {a : Action} {rest : List Action}
      (head : Step s a t)
      (tail : Exec t rest u) :
      Exec s (a :: rest) u

theorem exec_append
    {s t u : State} {first second : List Action}
    (hFirst : Exec s first t)
    (hSecond : Exec t second u) :
    Exec s (first ++ second) u := by
  induction hFirst with
  | nil => exact hSecond
  | cons head tail ih => exact Exec.cons head (ih hSecond)

def TaskGoal : TaskId → State → Prop
  | TaskId.task1, s =>
      s.worldCompleted = true ∧ 0 < s.keysCollected
  | TaskId.task2, s =>
      s.worldCompleted = true ∧ 0 < s.monstersKilled ∧ 0 < s.keysCollected
  | TaskId.task3, s =>
      s.worldCompleted = true ∧
      0 < s.monstersKilled ∧
      0 < s.keysCollected ∧
      2 ≤ s.visitedRooms.length
  | TaskId.task4, s =>
      s.worldCompleted = true ∧
      0 < s.keysCollected ∧
      s.hasSword = true ∧
      0 < s.monstersKilled ∧
      0 < s.gold
  | TaskId.task5, s =>
      s.worldCompleted = true ∧
      s.worldChestsRemaining = 0 ∧
      0 < s.chestsOpened ∧
      0 < s.keysCollected ∧
      0 < s.gold ∧
      0 < s.buttonsPressed

def TaskCompletable (task : TaskId) (initial : State) : Prop :=
  ∃ plan final, Exec initial plan final ∧ TaskGoal task final

end NesyLink

/-!
  Verifiable policy layer corresponding to `vision.py`, `planner.py`, and the
  shared room-memory machinery used by controllers 3--5.

  Neural inference is intentionally outside the proof boundary.  The Lean
  contract states exactly what the downstream verified layer needs from vision:
  obstacles and hazards may be over-approximated, while a detected active bridge
  must really be active.  Under that contract, planner safety transfers to the
  true symbolic state.
-/

namespace NesyLink

abbrev Path := List Position

def ListSubset {α : Type} (xs ys : List α) : Prop :=
  ∀ x, x ∈ xs → x ∈ ys

structure PerceptionContract (observed actual : State) : Prop where
  samePlayer : observed.player = actual.player
  walls : ListSubset actual.walls observed.walls
  traps : ListSubset actual.traps observed.traps
  gaps : ListSubset actual.gaps observed.gaps
  npcs : ListSubset actual.npcs observed.npcs
  chests : ListSubset (chestPositions actual) (chestPositions observed)
  openedChests :
    ListSubset (openedChestPositions actual) (openedChestPositions observed)
  monsters : ListSubset (monsterPositions actual) (monsterPositions observed)
  bridges : ListSubset (activeBridges observed) (activeBridges actual)

theorem perceived_safe_is_actually_safe
    {observed actual : State} {p : Position}
    (hContract : PerceptionContract observed actual)
    (hSafe : isSafe observed p) :
    isSafe actual p := by
  rcases hSafe with
    ⟨⟨hBounds, hWalls, hMonsters, hChests, hOpened, hNpcs⟩,
      hTraps, hGaps⟩
  refine ⟨⟨hBounds, ?_, ?_, ?_, ?_, ?_⟩, ?_, ?_⟩
  · intro h
    exact hWalls (hContract.walls p h)
  · intro h
    exact hMonsters (hContract.monsters p h)
  · intro h
    exact hChests (hContract.chests p h)
  · intro h
    exact hOpened (hContract.openedChests p h)
  · intro h
    exact hNpcs (hContract.npcs p h)
  · by_cases hActualTrap : p ∈ actual.traps
    · right
      have hObservedTrap : p ∈ observed.traps :=
        hContract.traps p hActualTrap
      rcases hTraps with hNotTrap | hBridge
      · exact False.elim (hNotTrap hObservedTrap)
      · exact hContract.bridges p hBridge
    · exact Or.inl hActualTrap
  · by_cases hActualGap : p ∈ actual.gaps
    · right
      have hObservedGap : p ∈ observed.gaps :=
        hContract.gaps p hActualGap
      rcases hGaps with hNotGap | hBridge
      · exact False.elim (hNotGap hObservedGap)
      · exact hContract.bridges p hBridge
    · exact Or.inl hActualGap

def MoveAction (a : Action) : Prop :=
  a ∈ [Action.up, Action.down, Action.left, Action.right]

def ActionAllowed (s : State) : Action → Prop
  | Action.wait => True
  | Action.shield => s.hasShield = true
  | Action.up => isSafe s (nextPosition s.player Action.up)
  | Action.down => isSafe s (nextPosition s.player Action.down)
  | Action.left => isSafe s (nextPosition s.player Action.left)
  | Action.right => isSafe s (nextPosition s.player Action.right)
  | Action.attack =>
      (∃ m, CanAttackMonster s m) ∨
      (∃ c, CanOpenChest s c) ∨
      (∃ sw, CanActivateSwitch s sw)

noncomputable def maskedAction (s : State) (proposed : Action) : Action :=
  letI := Classical.propDecidable (ActionAllowed s proposed)
  if ActionAllowed s proposed then proposed else Action.wait

theorem masked_action_allowed (s : State) (proposed : Action) :
    ActionAllowed s (maskedAction s proposed) := by
  unfold maskedAction
  split
  · assumption
  · simp [ActionAllowed]

theorem allowed_move_targets_safe
    {s : State} {a : Action}
    (hAllowed : ActionAllowed s a)
    (hMove : MoveAction a) :
    isSafe s (nextPosition s.player a) := by
  cases a with
  | wait => simp [MoveAction] at hMove
  | up => simpa [ActionAllowed] using hAllowed
  | down => simpa [ActionAllowed] using hAllowed
  | left => simpa [ActionAllowed] using hAllowed
  | right => simpa [ActionAllowed] using hAllowed
  | attack => simp [MoveAction] at hMove
  | shield => simp [MoveAction] at hMove

def VerifiedMove (s : State) (a : Action) (t : State) : Prop :=
  MoveAction a ∧
  ActionAllowed s a ∧
  t = moveResult s a

theorem verified_move_preserves_safe_state
    {s t : State} {a : Action}
    (hAlive : 0 < s.health)
    (hMove : VerifiedMove s a t) :
    SafeState t := by
  rcases hMove with ⟨hAction, hAllowed, rfl⟩
  have hSafe := allowed_move_targets_safe hAllowed hAction
  cases a <;> simp [MoveAction] at hAction
  all_goals simpa [SafeState, moveResult, actionDirection?, nextPosition] using
    And.intro hAlive hSafe

theorem masked_move_is_safe_for_actual_state
    {observed actual : State} {proposed : Action}
    (hContract : PerceptionContract observed actual)
    (hMove : MoveAction (maskedAction observed proposed)) :
    isSafe actual
      (nextPosition actual.player (maskedAction observed proposed)) := by
  have hObserved := allowed_move_targets_safe
    (masked_action_allowed observed proposed) hMove
  simpa [← hContract.samePlayer] using
    perceived_safe_is_actually_safe hContract hObserved

def PathStartsAt (path : Path) (start : Position) : Prop :=
  path.head? = some start

def PathEndsIn (path : Path) (goals : List Position) : Prop :=
  ∃ last, path.getLast? = some last ∧ last ∈ goals

def PathSafe (s : State) (path : Path) : Prop :=
  ∀ tile, tile ∈ path → isSafe s tile

def PathAdjacent : Path → Prop
  | [] => True
  | [_] => True
  | a :: b :: rest => adjacent a b ∧ PathAdjacent (b :: rest)

def PlannerSound (s : State) (goals : List Position) (path : Path) : Prop :=
  PathStartsAt path s.player ∧
  PathEndsIn path goals ∧
  PathSafe s path ∧
  PathAdjacent path

/- Proof-facing return contract for Python `bfs_path`.  The executable bounded
   BFS and its completeness theorem appear below. -/
def BFSReturns (s : State) (goals : List Position) (path : Path) : Prop :=
  PlannerSound s goals path

theorem bfs_return_starts_at_player
    {s : State} {goals : List Position} {path : Path}
    (h : BFSReturns s goals path) :
    PathStartsAt path s.player := h.1

theorem bfs_return_ends_in_goal
    {s : State} {goals : List Position} {path : Path}
    (h : BFSReturns s goals path) :
    PathEndsIn path goals := h.2.1

theorem bfs_return_path_safe
    {s : State} {goals : List Position} {path : Path}
    (h : BFSReturns s goals path) :
    PathSafe s path := h.2.2.1

theorem bfs_return_path_adjacent
    {s : State} {goals : List Position} {path : Path}
    (h : BFSReturns s goals path) :
    PathAdjacent path := h.2.2.2

def AdjacentGoal (s : State) (targets : List Position) (p : Position) : Prop :=
  isSafe s p ∧ ∃ target, target ∈ targets ∧ adjacent p target

theorem adjacent_goal_sound
    {s : State} {targets : List Position} {p : Position}
    (h : AdjacentGoal s targets p) :
    isSafe s p ∧ ∃ target, target ∈ targets ∧ adjacent p target := h

/- Tile-edge encoding used by `action_from_step` and
   `actions_for_tile_path`. -/
inductive EncodesTileStep : Position → Position → Action → Prop where
  | up (p : Position) (inside : 0 < p.2) :
      EncodesTileStep p (p.1, p.2 - 1) Action.up
  | down (p : Position) :
      EncodesTileStep p (p.1, p.2 + 1) Action.down
  | left (p : Position) (inside : 0 < p.1) :
      EncodesTileStep p (p.1 - 1, p.2) Action.left
  | right (p : Position) :
      EncodesTileStep p (p.1 + 1, p.2) Action.right

theorem encoded_tile_step_is_move
    {a b : Position} {action : Action}
    (h : EncodesTileStep a b action) :
    MoveAction action := by
  cases h <;> simp [MoveAction]

theorem encoded_tile_step_adjacent
    {a b : Position} {action : Action}
    (h : EncodesTileStep a b action) :
    adjacent a b := by
  cases h with
  | up inside =>
      have hNotLe : ¬ a.2 ≤ a.2 - 1 := by omega
      simp [adjacent, manhattan, hNotLe]
      omega
  | down => simp [adjacent, manhattan]
  | left inside =>
      have hNotLe : ¬ a.1 ≤ a.1 - 1 := by omega
      simp [adjacent, manhattan, hNotLe]
      omega
  | right => simp [adjacent, manhattan]

inductive ActionsFollowPath : Path → List Action → Prop where
  | empty : ActionsFollowPath [] []
  | singleton (p : Position) : ActionsFollowPath [p] []
  | cons
      {a b : Position} {rest : Path} {action : Action} {tail : List Action}
      (step : EncodesTileStep a b action)
      (remaining : ActionsFollowPath (b :: rest) tail) :
      ActionsFollowPath
        (a :: b :: rest)
        (List.replicate tileSize action ++ tail)

theorem actions_for_path_are_moves
    {path : Path} {actions : List Action}
    (h : ActionsFollowPath path actions) :
    ∀ action, action ∈ actions → MoveAction action := by
  induction h with
  | empty => simp
  | singleton => simp
  | @cons a b rest action tail step remaining ih =>
      intro candidate hCandidate
      simp only [List.mem_append, List.mem_replicate] at hCandidate
      rcases hCandidate with hBlock | hTail
      · rcases hBlock with ⟨_, rfl⟩
        exact encoded_tile_step_is_move step
      · exact ih candidate hTail

theorem actions_follow_adjacent_path
    {path : Path} {actions : List Action}
    (h : ActionsFollowPath path actions) :
    PathAdjacent path := by
  induction h with
  | empty => trivial
  | singleton => trivial
  | cons step remaining ih =>
      exact ⟨encoded_tile_step_adjacent step, ih⟩

/- Executable bounded BFS over the current room.  It intentionally retains
   duplicate nodes; duplicates affect efficiency, not reachability. -/
def moveActions : List Action :=
  [Action.up, Action.down, Action.left, Action.right]

theorem move_action_mem (a : Action) (h : MoveAction a) :
    a ∈ moveActions := by
  cases a <;> simp [MoveAction, moveActions] at h ⊢

instance decidableMoveAction (a : Action) : Decidable (MoveAction a) := by
  unfold MoveAction
  infer_instance

instance decidableIsSafe (s : State) (p : Position) : Decidable (isSafe s p) := by
  unfold isSafe walkable inBounds
  infer_instance

def plannerStep (s : State) (p : Position) (a : Action) : Position :=
  if MoveAction a ∧ isSafe s (nextPosition p a)
  then nextPosition p a
  else p

theorem planner_step_safe
    {s : State} {p : Position} {a : Action}
    (hStart : isSafe s p) :
    isSafe s (plannerStep s p a) := by
  unfold plannerStep
  split
  · rename_i h
    exact h.2
  · exact hStart

def runMoves (s : State) : Position → List Action → Position
  | p, [] => p
  | p, a :: rest => runMoves s (plannerStep s p a) rest

theorem run_moves_safe
    {s : State} {start : Position}
    (plan : List Action)
    (hStart : isSafe s start) :
    isSafe s (runMoves s start plan) := by
  induction plan generalizing start with
  | nil => exact hStart
  | cons a rest ih =>
      exact ih (planner_step_safe hStart)

def expandFrontier (s : State) : List Position → List Position
  | [] => []
  | p :: rest =>
      moveActions.map (plannerStep s p) ++ expandFrontier s rest

theorem planner_step_mem_expand
    {s : State} {p : Position} {frontier : List Position}
    (a : Action)
    (hAction : MoveAction a)
    (hPosition : p ∈ frontier) :
    plannerStep s p a ∈ expandFrontier s frontier := by
  induction frontier with
  | nil => cases hPosition
  | cons head tail ih =>
      simp [expandFrontier] at hPosition ⊢
      rcases hPosition with hEq | hTail
      · subst hEq
        exact Or.inl ⟨a, move_action_mem a hAction, rfl⟩
      · exact Or.inr (ih hTail)

def bfsVisited (s : State) : Nat → List Position → List Position
  | 0, frontier => frontier
  | n + 1, frontier =>
      frontier ++ bfsVisited s n (expandFrontier s frontier)

def bfsVisitedFrom (s : State) (start : Position) (depth : Nat) :
    List Position :=
  bfsVisited s depth [start]

theorem run_moves_mem_bfs
    {s : State} {start : Position} {frontier : List Position}
    (plan : List Action)
    {depth : Nat}
    (hStart : start ∈ frontier)
    (hMoves : ∀ a, a ∈ plan → MoveAction a)
    (hLength : plan.length ≤ depth) :
    runMoves s start plan ∈ bfsVisited s depth frontier := by
  induction depth generalizing start frontier plan with
  | zero =>
      cases plan with
      | nil => simpa [runMoves, bfsVisited] using hStart
      | cons a rest => cases hLength
  | succ depth ih =>
      cases plan with
      | nil => simp [runMoves, bfsVisited, hStart]
      | cons a rest =>
          have hA : MoveAction a := hMoves a (by simp)
          have hRest : ∀ b, b ∈ rest → MoveAction b := by
            intro b hb
            exact hMoves b (by simp [hb])
          have hRestLength : rest.length ≤ depth :=
            Nat.succ_le_succ_iff.mp hLength
          have hExpanded :
              plannerStep s start a ∈ expandFrontier s frontier :=
            planner_step_mem_expand a hA hStart
          have hTail := ih rest hExpanded hRest hRestLength
          simp [runMoves, bfsVisited]
          exact Or.inr hTail

def BoundedReachable
    (s : State) (start target : Position) (depth : Nat) : Prop :=
  ∃ plan,
    plan.length ≤ depth ∧
    (∀ a, a ∈ plan → MoveAction a) ∧
    runMoves s start plan = target

def BoundedGoalReachable
    (s : State) (start : Position) (goals : List Position) (depth : Nat) : Prop :=
  ∃ target, BoundedReachable s start target depth ∧ target ∈ goals

def BfsFindsGoal (visited goals : List Position) : Prop :=
  ∃ target, target ∈ visited ∧ target ∈ goals

theorem bfs_complete_for_bounded_goal
    {s : State} {start : Position} {goals : List Position} {depth : Nat}
    (hReachable : BoundedGoalReachable s start goals depth) :
    BfsFindsGoal (bfsVisitedFrom s start depth) goals := by
  rcases hReachable with ⟨target, ⟨plan, hLen, hMoves, hRun⟩, hGoal⟩
  refine ⟨target, ?_, hGoal⟩
  rw [← hRun]
  exact run_moves_mem_bfs plan (by simp) hMoves hLen

/- Multi-room memory and bounded room-graph BFS used by `RoomExplorer` and the
   Task 3 controller. -/
structure RoomEdge where
  source : RoomId
  direction : Direction
  target : RoomId
  deriving DecidableEq, Repr

structure RoomMemory where
  current : RoomId
  visited : List RoomId
  edges : List RoomEdge
  blocked : List (RoomId × Direction)
  keyGated : List (RoomId × Direction)
  deriving DecidableEq, Repr

def MemoryConsistent (memory : RoomMemory) : Prop :=
  memory.current ∈ memory.visited ∧
  ∀ edge, edge ∈ memory.edges →
    edge.source ∈ memory.visited ∧ edge.target ∈ memory.visited

def recordTransition (memory : RoomMemory) (edge : RoomEdge) : RoomMemory :=
  {
    memory with
    current := edge.target
    visited := edge.target :: memory.visited
    edges := edge :: memory.edges
  }

theorem record_transition_current
    (memory : RoomMemory) (edge : RoomEdge) :
    (recordTransition memory edge).current = edge.target := rfl

theorem record_transition_preserves_consistency
    {memory : RoomMemory} {edge : RoomEdge}
    (hConsistent : MemoryConsistent memory)
    (hSource : edge.source = memory.current) :
    MemoryConsistent (recordTransition memory edge) := by
  constructor
  · simp [recordTransition]
  · intro candidate hCandidate
    simp [recordTransition] at hCandidate ⊢
    rcases hCandidate with hNew | hOld
    · subst hNew
      constructor
      · right
        rw [hSource]
        exact hConsistent.1
      · left
        rfl
    · rcases hConsistent.2 candidate hOld with ⟨hFrom, hTo⟩
      exact ⟨Or.inr hFrom, Or.inr hTo⟩

abbrev RoomNeighbors := RoomId → List RoomId

def expandRooms (neighbors : RoomNeighbors) : List RoomId → List RoomId
  | [] => []
  | room :: rest => neighbors room ++ expandRooms neighbors rest

theorem room_neighbor_mem_expand
    {neighbors : RoomNeighbors} {room next : RoomId}
    {frontier : List RoomId}
    (hRoom : room ∈ frontier)
    (hNext : next ∈ neighbors room) :
    next ∈ expandRooms neighbors frontier := by
  induction frontier with
  | nil => cases hRoom
  | cons head tail ih =>
      simp [expandRooms] at hRoom ⊢
      rcases hRoom with hEq | hTail
      · subst hEq
        exact Or.inl hNext
      · exact Or.inr (ih hTail)

inductive RoomExec (neighbors : RoomNeighbors) :
    RoomId → List RoomId → RoomId → Prop where
  | nil (room : RoomId) : RoomExec neighbors room [] room
  | cons
      {room next target : RoomId} {rest : List RoomId}
      (hNext : next ∈ neighbors room)
      (hTail : RoomExec neighbors next rest target) :
      RoomExec neighbors room (next :: rest) target

def bfsRooms (neighbors : RoomNeighbors) : Nat → List RoomId → List RoomId
  | 0, frontier => frontier
  | n + 1, frontier =>
      frontier ++ bfsRooms neighbors n (expandRooms neighbors frontier)

theorem room_exec_mem_bfs
    {neighbors : RoomNeighbors} {start target : RoomId}
    {route : List RoomId} {frontier : List RoomId} {depth : Nat}
    (hExec : RoomExec neighbors start route target)
    (hStart : start ∈ frontier)
    (hLength : route.length ≤ depth) :
    target ∈ bfsRooms neighbors depth frontier := by
  induction hExec generalizing depth frontier with
  | nil room =>
      cases depth with
      | zero => simpa [bfsRooms] using hStart
      | succ n => simp [bfsRooms, hStart]
  | @cons room next target rest hNext hTail ih =>
      cases depth with
      | zero => cases hLength
      | succ depth =>
          have hExpanded : next ∈ expandRooms neighbors frontier :=
            room_neighbor_mem_expand hStart hNext
          have hRestLength : rest.length ≤ depth :=
            Nat.succ_le_succ_iff.mp hLength
          have hFound := ih hExpanded hRestLength
          simp [bfsRooms]
          exact Or.inr hFound

def RoomBoundedReachable
    (neighbors : RoomNeighbors) (start target : RoomId) (depth : Nat) : Prop :=
  ∃ route, route.length ≤ depth ∧ RoomExec neighbors start route target

theorem room_bfs_complete
    {neighbors : RoomNeighbors} {start target : RoomId} {depth : Nat}
    (hReachable : RoomBoundedReachable neighbors start target depth) :
    target ∈ bfsRooms neighbors depth [start] := by
  rcases hReachable with ⟨route, hLength, hExec⟩
  exact room_exec_mem_bfs hExec (by simp) hLength

end NesyLink

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

