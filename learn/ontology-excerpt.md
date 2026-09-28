# Current north-star layer of the aiida-reharness extension (excerpt)

Namespaces:
- base: `http://www.semanticweb.org/ivan/ontologies/2024/0/ontomat#`
- ext:  `https://mpds.io/ontology#` (prefix `:` in Turtle)

## Classes
- `:ComputationalWorkflow` ⊑ `:ComputationalArtefact` — a workchain
  composition computing material properties.
- `:WorkChainStep` ⊑ `:ComputationalArtefact` — one AiiDA workchain in a
  composition.
- `:SeebeckWorkflow`, `:PhononWorkflow` ⊑ `:ComputationalWorkflow`.
- base `:Property` — the materials-ontology property class (hasCategory /
  hasDomain / hasUnits datatype props exist in the base).

## Properties
- `:hasTargetProperty` — domain `:CampaignPlan`, range base `:Property`.
- `:realizedBy` — domain base `:Property`, range `:ComputationalWorkflow`.
- `:hasStep` — domain `:ComputationalWorkflow`, range `:WorkChainStep`.

## Existing individuals (DO NOT redefine; REUSE where applicable)
- Steps: `:wc_fleur_scf` (fleur.mpds SCF + geometry optimization),
  `:wc_fleur_dos` (fleur.dos_seebeck), `:wc_crystal_scf` (crystal.mpds),
  `:wc_crystal_seebeck` (crystal.mpds_seebeck), `:wc_phonon` (phonon stage,
  CRYSTAL FREQCALC + PREOPTGEOM-inside-block).
- Workflows: `:wf_fleur_seebeck` (SeebeckWorkflow; steps wc_fleur_scf,
  wc_fleur_dos), `:wf_crystal_seebeck` (SeebeckWorkflow; steps wc_crystal_scf,
  wc_crystal_seebeck), `:wf_crystal_phonon` (PhononWorkflow; steps
  wc_crystal_scf, wc_phonon).

## Task-layer context (for precondition reuse)
- `:CalculationTask` with `:hasEngine` ∈ {`:fleur`, `:pcrystal`} (yascheduler
  engine keys), `:hasSubmitChannel` ∈ {`:AiiDAWorkChain`,
  `:DirectYaschedulerAPI`}, `:hasSystem` → `:DFTSystem`.
- Gate classes already enforce mitigations: `:NeedsJUDFTWarnOnly`
  (f-element systems), `:NeedsSphereCaps` (Ba/Cs/Rb/K systems),
  `:DirectFLEURSubmit` (nohup + JUDFT in spawn).

## Conventions for new axioms
- New steps named `:wc_<entry_point>` after the REAL AiiDA entry point
  (e.g. `fleur.mae` ⇒ `:wc_fleur_mae`), each with a one-line rdfs:comment.
- New property individuals live in the BASE namespace ONLY if the property
  already exists there; otherwise use a fresh `:prop_<name>` individual in
  the ext namespace typed base `:Property`.
- New workflow classes follow `<Property>Workflow ⊑ ComputationalWorkflow`
  with an `owl:equivalentClass` (⊓ + ∃) definition where a sufficient
  condition is intended.