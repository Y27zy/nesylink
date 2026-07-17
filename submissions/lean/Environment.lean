/-!
  Environment formalization skeleton for NesyLink mathematical-logic tasks.

  This file should model the symbolic state produced by `vision.py`, not the
  raw RGB frame or the full Python engine.
-/

namespace NesyLink

abbrev Position := Nat × Nat

inductive Action where
  | wait
  | up
  | down
  | left
  | right
  | attack
  | shield
  deriving DecidableEq, Repr

structure State where
  player : Position
  walls : List Position
  traps : List Position
  chests : List Position
  openedChests : List Position
  exits : List Position
  monsters : List Position
  npcs : List Position
  buttons : List Position
  switches : List Position
  bridges : List Position
  gaps : List Position
  keys : Nat
  gold : Nat
  deriving Repr

def inBounds (p : Position) : Prop :=
  p.1 < 10 ∧ p.2 < 8

def manhattan (a b : Position) : Nat :=
  let dx := if a.1 ≤ b.1 then b.1 - a.1 else a.1 - b.1
  let dy := if a.2 ≤ b.2 then b.2 - a.2 else a.2 - b.2
  dx + dy

def adjacent (a b : Position) : Prop :=
  manhattan a b = 1

def nextPosition (p : Position) : Action → Position
  | Action.up => (p.1, p.2 - 1)
  | Action.down => (p.1, p.2 + 1)
  | Action.left => (p.1 - 1, p.2)
  | Action.right => (p.1 + 1, p.2)
  | _ => p

def isSafe (s : State) (p : Position) : Prop :=
  inBounds p ∧
  p ∉ s.walls ∧
  p ∉ s.monsters ∧
  p ∉ s.chests ∧
  p ∉ s.openedChests ∧
  p ∉ s.npcs ∧
  (p ∉ s.traps ∨ p ∈ s.bridges) ∧
  (p ∉ s.gaps ∨ p ∈ s.bridges)

def GoalReached (s : State) : Prop :=
  s.player ∈ s.exits

inductive Step : State → Action → State → Prop where
  | moveSafe
      {s : State} {a : Action} :
      a ∈ [Action.up, Action.down, Action.left, Action.right] →
      isSafe s (nextPosition s.player a) →
      Step s a { s with player := nextPosition s.player a }
  | moveBlocked
      {s : State} {a : Action} :
      a ∈ [Action.up, Action.down, Action.left, Action.right] →
      ¬ isSafe s (nextPosition s.player a) →
      Step s a s
  | wait {s : State} :
      Step s Action.wait s
  | shield {s : State} :
      Step s Action.shield s

def SafeState (s : State) : Prop :=
  isSafe s s.player

end NesyLink
