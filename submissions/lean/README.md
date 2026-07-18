# Lean proofs for Task 1–5

This folder is the submission copy of the Lean formalization.

- `Environment.lean`: symbolic state, bridge-aware safety predicate, and step model.
- `Strategy.lean`: BFS result contract, safe/adjacent paths, adjacent goals, and
  tile-path-to-action encoding.
- `TaskProofs.lean`: Task 1/2 phase properties, Task 3 priorities, **Task 4/5
  phase priorities and completion chains**, plus shared Task 3/4/5 composition
  lemmas.

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
