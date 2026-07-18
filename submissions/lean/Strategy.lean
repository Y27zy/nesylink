import «Environment»

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
