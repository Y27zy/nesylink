# Lean proofs for Task 1/2/3

This folder is the submission copy of the Lean formalization.

- `Environment.lean`: symbolic state, bridge-aware safety predicate, and step model.
- `Strategy.lean`: BFS result contract, safe/adjacent paths, adjacent goals, and
  tile-path-to-action encoding.
- `TaskProofs.lean`: Task 1/2 phase properties plus Task 3 monster/chest/key
  priorities and the monster-key-exit completion chain.

Check from the project root:

```powershell
lake build
lake env lean submissions\lean\TaskProofs.lean
```

The project currently targets `leanprover/lean4:v4.29.0-rc6` through
`lean-toolchain`.

Imports are intentionally short:

```lean
import «Environment»
import «Strategy»
```

The project `lakefile.lean` sets `srcDir := "submissions/lean"`, so these
imports resolve inside this folder.
