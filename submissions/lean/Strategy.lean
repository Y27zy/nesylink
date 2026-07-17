import «Environment»

/-!
  Verifiable contracts for the symbolic planner in `submissions/planner.py`.

  The RGB classifiers are outside the proof boundary.  These definitions start
  from the `State` supplied by vision and specify the safety, adjacency, BFS
  result, and tile-path-to-action properties checked at the planner boundary.
-/

namespace NesyLink

abbrev Path := List Position

def tileSize : Nat := 16

def MoveAction (a : Action) : Prop :=
  a ∈ [Action.up, Action.down, Action.left, Action.right]

def PathStartsAt (p : Path) (start : Position) : Prop :=
  p.head? = some start

def PathEndsIn (p : Path) (goals : List Position) : Prop :=
  ∃ last, p.getLast? = some last ∧ last ∈ goals

def PathSafe (s : State) (p : Path) : Prop :=
  ∀ tile, tile ∈ p → isSafe s tile

def PathAdjacent : Path → Prop
  | [] => True
  | [_] => True
  | a :: b :: rest => adjacent a b ∧ PathAdjacent (b :: rest)

def PlannerSound (s : State) (goals : List Position) (path : Path) : Prop :=
  PathStartsAt path s.player ∧
  PathEndsIn path goals ∧
  PathSafe s path ∧
  PathAdjacent path

/- `BFSReturns` is the proof-facing contract of Python's `bfs_path`: whenever
   the executable search returns a path, the returned path carries this
   certificate.  Search completeness and classifier correctness are separate
   assumptions and are not hidden as Lean axioms. -/
def BFSReturns (s : State) (goals : List Position) (path : Path) : Prop :=
  PlannerSound s goals path

theorem bfs_return_starts_at_player
    {s : State} {goals : List Position} {path : Path}
    (h : BFSReturns s goals path) :
    PathStartsAt path s.player :=
  h.1

theorem bfs_return_ends_in_goal
    {s : State} {goals : List Position} {path : Path}
    (h : BFSReturns s goals path) :
    PathEndsIn path goals :=
  h.2.1

theorem bfs_return_path_safe
    {s : State} {goals : List Position} {path : Path}
    (h : BFSReturns s goals path) :
    PathSafe s path :=
  h.2.2.1

theorem bfs_return_path_adjacent
    {s : State} {goals : List Position} {path : Path}
    (h : BFSReturns s goals path) :
    PathAdjacent path :=
  h.2.2.2

def AdjacentGoal (s : State) (targets : List Position) (p : Position) : Prop :=
  isSafe s p ∧ ∃ target, target ∈ targets ∧ adjacent p target

theorem adjacent_goal_sound
    {s : State} {targets : List Position} {p : Position}
    (h : AdjacentGoal s targets p) :
    isSafe s p ∧ ∃ target, target ∈ targets ∧ adjacent p target :=
  h

/- `EncodesTileStep a b action` matches `action_from_step(a, b)`: the action
   points from one adjacent tile to the next. -/
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
  | down =>
      simp [adjacent, manhattan]
  | left inside =>
      have hNotLe : ¬ a.1 ≤ a.1 - 1 := by omega
      simp [adjacent, manhattan, hNotLe]
      omega
  | right =>
      simp [adjacent, manhattan]

/- The relation mirrors `actions_for_tile_path`: each tile edge becomes exactly
   `tileSize` copies of its direction action, followed by the encoding of the
   remaining path. -/
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

theorem actions_for_single_tile_empty (p : Position) :
    ActionsFollowPath [p] [] :=
  ActionsFollowPath.singleton p

theorem actions_for_one_step_repeat
    {a b : Position} {action : Action}
    (h : EncodesTileStep a b action) :
    ActionsFollowPath [a, b] (List.replicate tileSize action) := by
  simpa using ActionsFollowPath.cons h (ActionsFollowPath.singleton b)

end NesyLink
