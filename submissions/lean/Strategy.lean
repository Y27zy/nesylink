import «Environment»

/-!
  Strategy formalization skeleton.

  Add planner, path, action-mask, and subgoal definitions here after the Python
  controller structure stabilizes.
-/

namespace NesyLink

abbrev Path := List Position

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

end NesyLink
