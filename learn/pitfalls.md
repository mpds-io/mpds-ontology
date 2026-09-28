# Operational experience the learned axioms must respect (pitfall digest)

New property→workflow axioms are only sound if they encode the KNOWN
operational constraints. Non-negotiables from the campaign experience:

1. **SCF-precondition (pitfalls 30, 22)**: every property workflow that reads
   a converged charge density (DOS/Seebeck, MAE, EOS, forces, band structure)
   REQUIRES a converged SCF stage first. Reuse `wc_fleur_scf` /
   `wc_crystal_scf` — never invent an SCF-less property route.
2. **Phonons (pitfalls 25, 27)**: imaginary frequencies ⇒ geometry was not
   fully optimized. CRYSTAL needs `PREOPTGEOM` INSIDE the `FREQCALC` block
   (a sibling keyword crashes with MPI_ABORT). Phonon workflows carry the
   geometry-optimization precondition explicitly.
3. **Geometry optimization (pitfalls 15, 23, 40)**: CDG optimizers cost
   1+N SCF evals per CG iteration; use `delta: 0.01` Å, `tolerance: 0.05`
   Htr/Å (defaults are noise / instant-converge traps). One failed eval =
   penalty 1e10; if ALL evals of an iteration fail ⇒ optimizer exits 497.
4. **f-elements (pitfalls 8c, 9)**: JUDFT_WARN_ONLY required (ghost states).
   Do NOT claim DFT+HIA/DFT+U needed without plain-PBE evidence first; 4f
   occupation fluctuation is NORMAL — gate on energy stability, not raw
   distance.
5. **Ba/Cs/Rb/K systems (pitfall 37)**: per-system MT-sphere caps required
   (`differ 2` at setup otherwise); species-level edits live in per-system
   templates only (pitfall 38).
6. **Direct yascheduler submissions (pitfalls 31, 32)**: spawn needs nohup +
   JUDFT_WARN_ONLY; AiiDA submissions stage these automatically.
7. **Mixing scheme (pitfalls 15, 22b)**: Anderson alpha=0.15 only; Broyden1/2
   are NOT implemented in FLEUR 6.2; straight mixing fails hard systems.
8. **Serial campaigns (pitfalls 20, 33)**: one system at a time, one engine
   owning all cores; clean stale waiting workchains BEFORE launching.
9. **Infra vs physics (pitfall 42)**: a uniform fast batch of 412s with clean
   evaluator CalcJobs = INFRA signature — never answer with SCF tuning.

Workflow-step individuals may carry these as `requires`-style comments; the
gate classes (`NeedsJUDFTWarnOnly`, `NeedsSphereCaps`, `DirectFLEURSubmit`)
already enforce 4, 5, 6 at plan level — the learned axioms must not bypass
them (properties flow THROUGH tasks that already carry the gates).