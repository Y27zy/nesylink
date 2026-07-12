# Lean proofs for Task 1/2

This folder is the submission copy of the Lean formalization.

- `Environment.lean`: symbolic state and step model.
- `Strategy.lean`: path-level planner properties.
- `TaskProofs.lean`: Task 1 key-exit chain and Task 2 kill-key-exit chain.

Check from the project root:

```powershell
lake build
lake env lean submissions\lean\TaskProofs.lean
```

Imports are intentionally short:

```lean
import «Environment»
import «Strategy»
```

The project `lakefile.lean` sets `srcDir := "submissions/lean"`, so these
imports resolve inside this folder.
