# LEAN/OWL2 rule & proof vocabulary (distilled for axiom mining)

Sources: kobayashi-marust (km) Lean 4 certification corpus — sorry-free
soundness/completeness for the ELC / hypertableau / CB publication boundaries
and the automatic routing composition; lean-sroiq-sdd (ELKSDD) — mechanized
EL→SROIQ saturation calculus with per-rule soundness lemmas.

## What each DL construct costs the reasoner (routing consequences)
- **EL/EL++ (ELC route)**: conjunction ⊓, existential ∃R.C, top ⊤, bottom ⊥,
  role chains, range restrictions. Polynomial saturation. Our *core* should
  stay here: `⊓`-conjunctions, `∃R.C` restrictions, named-class hierarchies.
- **ALC adds**: negation ¬C, disjunction ⊔, universal ∀R.C. Boolean closure;
  consequence-based engines ground to clauses (disjunctions) — more work.
- **ALCHOQ adds**: nominals {a}, qualified cardinality ≥n R.C / ≤n R.C.
- **SROIQ adds**: role axioms (trans, sym, asym, inv, chain, disjoint).

## Rules for OUR axioms (what the certificates rely on)
1. Prefer `⊓` + `∃` shapes — they classify in every route (ELC-compatible
   when no negation/nominals are involved).
2. `equivalentClass (C ⊓ restriction)` gives SUFFICIENT conditions (instance
   classification); bare `subClassOf` restrictions are only NECESSARY —
   a plan individual won't classify into them (verified empirically, both
   pyfactxx and km).
3. Boolean consistency gates = `subClassOf hasValue true` on FUNCTIONAL
   datatype properties (clash proven in both backends at the assertion level).
4. Disjointness: pairwise `owl:disjointWith` (AllDisjointClasses is not
   mapped by km; pairwise is EL-friendlier).
5. No `rdfs:subPropertyOf` (km mapper gap) — domain/range carry the semantics.
6. A TBox taxonomy + consistency verdict from the Lean-certified engine (km)
   is the certification view; plan gates (ABox instance clashes) run on
   pyfactxx. New axioms must keep BOTH sound: the delta is loaded on top of
   base+extension and the merged KB must classify consistent with zero new
   unsatisfiable classes.

## Saturation-rule names (for rationale.md citations)
ELK: R0 (init), R⊤ (top), R⊑ (role inclusion), R⁻⊓/R⁺⊓ (conjunction
propagation), R⊥ (bottom), R⁺∃ (existential propagation — requires the
acyclicity side condition), R⊥-∃.
CB (consequence-based, km): context-structure rules — the twelve Tena Cucala
rules; hypertableau blocking for the disjunctive routes.
Python-parity pattern (ELKSDD.SROIQPythonParity): every emitted clause shape
pairs with a named Lean soundness lemma — mirror this discipline: every new
axiom shape we introduce must reduce to shapes with existing soundness lemmas
(⊓, ∃, hasValue-on-functional, pairwise-disjoint, domain/range).