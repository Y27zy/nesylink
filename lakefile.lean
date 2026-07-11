import Lake
open Lake DSL

package «nesylink» where

@[default_target]
lean_lib «NesyLinkProofs» where
  srcDir := "lean"
  roots := #[`Environment, `Strategy, `TaskProofs]
