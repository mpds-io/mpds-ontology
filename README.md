# MPDS neuro-symbolic data mining

# aiida-reharness ontology extension

An additive extension of the [MPDS materials ontology](https://github.com/mpds-io/mpds-ontology)
(`mpds_ontology.rdf`, imported unchanged) that encodes the **aiida-reharness** project's
ontology plus the lab's collected operational experience, so that campaign plans can be
*reasoned about* before compute is spent.

## Layout

```
mpds_ontology.rdf              # upstream base ontology (untouched, imported)
aiida_reharness.rdf            # the extension (generated - do not edit by hand)
gen_aiida_reharness.py          # generator: experience corpus -> RDF/XML
validate_aiida_reharness.py     # FaCT++ gate suite (23 checks, exit 0 = green)
scratch/                       # working notes (pitfalls_full.md = extracted corpus)
```

`aiida_reharness.rdf` is **generated** — all edits go into `gen_aiida_reharness.py`,
then `python3 gen_aiida_reharness.py`. The base ontology is better to leave unmodified: the
extension only *adds* axioms about base individuals (e.g. `Gd` is additionally
typed `HeavyElement`), however the edits into base are possible.

## The three layers

1. **Computation** — engines (FLEUR/CRYSTAL/Inpgen), compute nodes, platforms,
   submit channels (AiiDA workchain vs direct yascheduler API), AiiDA exit-code
   families, FLEUR mixing schemes, and the aiida-reharness FSM layers
   (Orchestration / Compute / Reasoning — the time-scale split).
2. **Campaign plans** — `CampaignPlan`/`DFTSystem`/`CalculationTask` individuals
   with *detection classes* the reasoner infers (`FElementSystem`,
   `LargeSphereCationSystem`, `TaskExit412`, `InfraSignatureBatch`, ...).
3. **Experience** — the mpds-aiida pitfall corpus (44+ entries) as
   `EngineFailureMode` individuals: signature regex, pitfall ref, fix, evidence
   command, and FSM routing (code/agent/approval/wait state kind).

## Reasoning gates (the point of all this)

Mitigation-required classes carry **subClassOf hasValue restrictions on
functional boolean data properties**. A plan that misses a required mitigation
does not merely get flagged — the KB becomes **INCONSISTENT** and the kernel
fails loud (`classify()` raises). This is the ontology-level analog of
reharness's fail-loud invariant; the gates currently encoded:

| Gate | Fires when | Pitfall |
|---|---|---|
| `NeedsJUDFTWarnOnly` | f-element system, mitigation not asserted true | 8c, 32 |
| `NeedsSphereCaps` | Ba/Cs/Rb/K system without per-system sphere caps + templates | 37, 38 |
| `DirectFLEURSubmit` | FLEUR via direct API without nohup + JUDFT_WARN_ONLY in spawn | 31, 32 |
| `PRDApprovedPlan` | plan run without an approved PRD | reharness PRD gate |

Detection-only (flag, not fatal): `BroydenOnFLEUR62` (pitfall 15),
`InfraSignatureBatch` (pitfall 42: uniform fast 412s + clean evals = infra,
never physics).

## Verified kernel facts (pyfactxx refactoring-synthesis, 79/79 tests)

- Object-property `hasValue` and datatype-property `hasValue` classify
  individuals into equivalentClass-intersection definitions — both directions
  (positive and negative control) verified.
- **Functional data properties are mandatory for boolean gates**: a
  multi-valued `p=false` does not contradict a gate's `p=true` (both coexist);
  functional turns the gate into a real clash.
- **FaCT++ realisation does not classify instances into forall-defined
  classes** (∀R.C; verified empirically, kernel-level). "All tasks exit 412"
  therefore became a closed-world builder assertion (`hasAllTasksExit412`)
  instead of an `allValuesFrom` axiom — the validator computes it from task
  states, per the aiida-reharness closed-world plan-booleans design.
- Coras SPARQL layer emits anonymous BNodes for realized types; instance
  checks must use `reasoner.is_instance()` against named classes.
- The kernel is fail-loud: `classify()` raises `RuntimeError: Inconsistent
  KB` — a gate firing IS the compile-time plan rejection.

## Usage

```bash
# regenerate after editing the generator
python3 gen_aiida_reharness.py

# validate against FaCT++ (needs pyfactxx built from the refactoring-synthesis branch)
python3 validate_aiida_reharness.py
```
