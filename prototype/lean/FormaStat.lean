/-
  FormaStat corpus root.

  `lake build` of the `FormaStat` lib builds this module and everything it
  imports. The autoformalization loop (`loop/run_loop.py`) appends
  `import FormaStat.Generated.<id>` lines below the marker as theorems are
  verified, so the whole corpus stays buildable.
-/

import FormaStat.Sanity

-- FORMASTAT-GENERATED-IMPORTS (do not edit this marker; the loop appends below it)
