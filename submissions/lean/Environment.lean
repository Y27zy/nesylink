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
