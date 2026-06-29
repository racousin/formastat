/-
  Sanity / Tier-0 — hand-written, NOT autoformalized.

  Purpose: validate the pinned toolchain end-to-end before the loop writes
  anything. If this file builds, then Mathlib resolved and the toolchain is
  coherent. (LeanCopilot is deferred — see lakefile.toml; gap-filling uses
  symbolic tactics instead.)

  This is Milestone-1's compile target.
-/

import Mathlib

namespace FormaStat.Sanity

-- 2 + 2 = 4
theorem two_add_two : (2 : ℕ) + 2 = 4 := by decide

-- additive identity on ℕ
theorem add_zero' (n : ℕ) : n + 0 = n := by simp

-- commutativity of addition on ℝ
theorem add_comm_real (a b : ℝ) : a + b = b + a := by ring

end FormaStat.Sanity
