/-!
  Task-level proof skeleton.

  Put concrete Task 1-5 subtask composition theorems here. Avoid unexplained
  `sorry`, `admit`, or `axiom` in the final submission.
-/

import «Strategy»

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

end NesyLink

