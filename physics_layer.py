# Physics-derivation layer: the Schrödinger root and its approximation DAG.
#
# DESIGN (non-breakable addition, per the Lean parity contract):
# - The equation itself is NEVER a DL axiom: OWL/DL cannot express calculus,
#   so equations are NAMED INDIVIDUALS of class PhysicalEquation carrying
#   their LaTeX and SymPy str() forms as xsd:string datatype properties
#   (the same km-proven shape as the pitfall hasSignature strings).
# - The derivation DAG is OBJECT property assertions between those
#   individuals (derivesFrom), transitive: chains of approximations compose.
# - No new axiom SHAPE is introduced: only the shapes both backends
#   already certify and OntologyParity.lean proves sound (equivalentClass
#   ∩-definitions, functional datatype properties, plain assertions).
#
# All SymPy strings are byte-identical to physics.py str() output —
# tests/test_physics_parity.py fails loud on drift.

ARH_NS = "https://mpds.io/ontology#"
XSD = "http://www.w3.org/2001/XMLSchema#"


def _A(local):
    return ARH_NS + local


def _X(t):
    return f'rdf:datatype="{XSD}{t}"'


PHYSICS_LAYER = [
    "<!-- ============ PHYSICS-DERIVATION LAYER ========================== -->",
    # --- classes / properties ------------------------------------------------
    f'<owl:Class rdf:about="{_A("PhysicalEquation")}">',
    f'\t<rdfs:subClassOf rdf:resource="{_A("ComputationalArtefact")}"/>',
    "\t<rdfs:comment>A named solid-state physics equation, carried as data "
    "(hasLatexForm, hasSymPyForm) — NEVER as DL axioms: description logic "
    "cannot express calculus. The executable content lives in physics.py "
    "(SymPy) and the AiiDA workchains; the ontology carries the derivation "
    "structure and the workflow bindings.</rdfs:comment>",
    "</owl:Class>",
    f'<owl:ObjectProperty rdf:about="{_A("derivesFrom")}">',
    f'\t<rdf:type rdf:resource="http://www.w3.org/2002/07/owl#TransitiveProperty"/>',
    f'\t<rdfs:domain rdf:resource="{_A("PhysicalEquation")}"/>',
    f'\t<rdfs:range rdf:resource="{_A("PhysicalEquation")}"/>',
    "\t<rdfs:comment>The approximation relation: a derived equation "
    "derivesFrom a more fundamental one (Kohn-Sham derivesFrom "
    "Schroedinger). Transitive: chains of approximations compose; every "
    "equation here reaches eq_schroedinger in finitely many steps.</rdfs:comment>",
    "</owl:ObjectProperty>",
    f'<owl:DatatypeProperty rdf:about="{_A("hasDerivationLevel")}">',
    '\t<rdf:type rdf:resource="http://www.w3.org/2002/07/owl#FunctionalProperty"/>',
    f'\t<rdfs:domain rdf:resource="{_A("PhysicalEquation")}"/>',
    f'\t<rdfs:range rdf:resource="{XSD}string"/>',
    "\t<rdfs:comment>Approximation level of the derivation (functional: one "
    "level per equation). exact / approximate / heuristic.</rdfs:comment>",
    "</owl:DatatypeProperty>",
    f'<owl:ObjectProperty rdf:about="{_A("computedBy")}">',
    f'\t<rdfs:domain rdf:resource="{_A("PhysicalEquation")}"/>',
    f'\t<rdfs:range rdf:resource="{_A("ComputationalWorkflow")}"/>',
    "\t<rdfs:comment>The executable workflow that computes the equation's "
    "quantities (realizedBy binds material properties to workflows; "
    "computedBy binds equations to them).</rdfs:comment>",
    "</owl:ObjectProperty>",
    f'<owl:DatatypeProperty rdf:about="{_A("hasLatexForm")}">',
    f'\t<rdfs:domain rdf:resource="{_A("PhysicalEquation")}"/>',
    f'\t<rdfs:range rdf:resource="{XSD}string"/>',
    "\t<rdfs:comment>MathJax-ready LaTeX of the equation, as typed in the literature.</rdfs:comment>",
    "</owl:DatatypeProperty>",
    f'<owl:DatatypeProperty rdf:about="{_A("hasSymPyForm")}">',
    f'\t<rdfs:domain rdf:resource="{_A("PhysicalEquation")}"/>',
    f'\t<rdfs:range rdf:resource="{XSD}string"/>',
    "\t<rdfs:comment>str() of the SymPy Eq in physics.py — byte-identical by "
    "construction; tests/test_physics_parity.py fails loud on drift.</rdfs:comment>",
    "</owl:DatatypeProperty>",
    # --- the ROOT: time-independent Schrödinger equation --------------------
    f'<rdf:Description rdf:about="{_A("eq_schroedinger")}">',
    f'\t<rdf:type rdf:resource="{_A("PhysicalEquation")}"/>',
    f'\t<hasDerivationLevel {_X("string")}>exact</hasDerivationLevel>',
    f'\t<hasLatexForm {_X("string")}>' + r"\hat{H}\Psi = E\Psi" + "</hasLatexForm>",
    f'\t<hasSymPyForm {_X("string")}>Eq(H*Psi, E*Psi)</hasSymPyForm>',
    "\t<rdfs:comment>The time-independent Schrödinger equation — the ROOT "
    "of the physics-derivation DAG. Non-relativistic stationary-state "
    "quantum mechanics; every DFT quantity in this ontology is derived "
    "from it by the chain below.</rdfs:comment>",
    "</rdf:Description>",
    # --- Kohn-Sham -----------------------------------------------------------
    f'<rdf:Description rdf:about="{_A("eq_kohn_sham")}">',
    f'\t<rdf:type rdf:resource="{_A("PhysicalEquation")}"/>',
    f'\t<derivesFrom rdf:resource="{_A("eq_schroedinger")}"/>',
    f'\t<hasDerivationLevel {_X("string")}>approximate</hasDerivationLevel>',
    f'\t<hasLatexForm {_X("string")}>' +
        r"\left(-\frac{1}{2}\nabla^2 + v_\mathrm{eff}\right)\psi_i = \varepsilon_i\psi_i" +
        "</hasLatexForm>",
    f'\t<hasSymPyForm {_X("string")}>Eq(psi_i*(-nabla**2/2 + v_eff), eps_i*psi_i)</hasSymPyForm>',
    "\t<rdfs:comment>The Kohn-Sham equations: exact-in-principle mapping of "
    "the interacting system onto non-interacting orbitals; approximations "
    "enter through the exchange-correlation functional.</rdfs:comment>",
    "</rdf:Description>",
    # --- DFT total-energy functional -----------------------------------------
    f'<rdf:Description rdf:about="{_A("eq_dft_energy")}">',
    f'\t<rdf:type rdf:resource="{_A("PhysicalEquation")}"/>',
    f'\t<derivesFrom rdf:resource="{_A("eq_schroedinger")}"/>',
    f'\t<hasDerivationLevel {_X("string")}>approximate</hasDerivationLevel>',
    f'\t<hasLatexForm {_X("string")}>' +
        r"E[n] = T_s[n] + \int v_\mathrm{ext} n\,d\mathbf{r} + J[n] + E_\mathrm{xc}[n]" +
        "</hasLatexForm>",
    f'\t<hasSymPyForm {_X("string")}>FunctionalForm:E[n] = T_s[n] + Integral(v_ext*n, r) + J[n] + E_xc[n]</hasSymPyForm>',
    "\t<rdfs:comment>The DFT total-energy functional: the variational "
    "object the SCF cycle minimizes; the energy whose differences the "
    "EOS/MAE workflows fit. The SymPy form is the functional-equation "
    "spelling (not an Eq — DFT energy is a functional of the density).</rdfs:comment>",
    "</rdf:Description>",
    # --- Hellmann-Feynman -----------------------------------------------------
    f'<rdf:Description rdf:about="{_A("eq_hellmann_feynman")}">',
    f'\t<rdf:type rdf:resource="{_A("PhysicalEquation")}"/>',
    f'\t<derivesFrom rdf:resource="{_A("eq_kohn_sham")}"/>',
    f'\t<hasDerivationLevel {_X("string")}>exact</hasDerivationLevel>',
    f'\t<hasLatexForm {_X("string")}>' + r"F_i = -\frac{\partial E}{\partial x_i}" + "</hasLatexForm>",
    f'\t<hasSymPyForm {_X("string")}>Eq(F, -Derivative(E, x))</hasSymPyForm>',
    "\t<rdfs:comment>Forces from the converged DFT total energy: the bridge "
    "from eq_dft_energy to geometry optimization and the fleur.forces "
    "workchain. Exact under Born-Oppenheimer (clamped nuclei) given an "
    "exactly converged density.</rdfs:comment>",
    "</rdf:Description>",
    # --- Birch-Murnaghan EOS --------------------------------------------------
    f'<rdf:Description rdf:about="{_A("eq_birch_murnaghan")}">',
    f'\t<rdf:type rdf:resource="{_A("PhysicalEquation")}"/>',
    f'\t<derivesFrom rdf:resource="{_A("eq_dft_energy")}"/>',
    f'\t<hasDerivationLevel {_X("string")}>heuristic</hasDerivationLevel>',
    f'\t<hasLatexForm {_X("string")}>' +
        r"E(V) = E_0 + \frac{9V_0B_0}{16}"
        r"\left[\left(\frac{V_0}{V}-1\right)^3 B_0'"
        r"+ \left(\frac{V_0}{V}-1\right)^2\left(6-4\frac{V_0}{V}\right)\right]" +
        "</hasLatexForm>",
    f'\t<hasSymPyForm {_X("string")}>'
    "Eq(E_c, 9*B_0*V_0*(B_0'*(-1 + V_0/V)**3 + (-1 + V_0/V)**2*(6 - 4*V_0/V))/16 + E_0)"
    "</hasSymPyForm>",
    "\t<rdfs:comment>3rd-order Birch-Murnaghan EOS: the analytic form fitted "
    "to the fleur.eos volume scan; its B_0 parameter IS the bulk modulus "
    "(prop_bulk_modulus).</rdfs:comment>",
    "</rdf:Description>",
    # --- MAE scan ------------------------------------------------------------
    f'<rdf:Description rdf:about="{_A("eq_mae_scan")}">',
    f'\t<rdf:type rdf:resource="{_A("PhysicalEquation")}"/>',
    f'\t<derivesFrom rdf:resource="{_A("eq_dft_energy")}"/>',
    f'\t<hasDerivationLevel {_X("string")}>heuristic</hasDerivationLevel>',
    f'\t<hasLatexForm {_X("string")}>' + r"E(\phi) = E_0 + K_u \sin^2(\phi)" + "</hasLatexForm>",
    f'\t<hasSymPyForm {_X("string")}>Eq(E_phi, E_0 + K_u*sin(phi)**2)</hasSymPyForm>',
    "\t<rdfs:comment>Magnetization-rotation scan: the symmetry form the "
    "fleur.mae workchain fits; K_u = E(90°) − E(0°) is the anisotropy "
    "(prop_magnetic_anisotropy).</rdfs:comment>",
    "</rdf:Description>",
    # --- phonon dispersion -----------------------------------------------------
    f'<rdf:Description rdf:about="{_A("eq_phonon_dispersion")}">',
    f'\t<rdf:type rdf:resource="{_A("PhysicalEquation")}"/>',
    f'\t<derivesFrom rdf:resource="{_A("eq_hellmann_feynman")}"/>',
    f'\t<hasDerivationLevel {_X("string")}>heuristic</hasDerivationLevel>',
    f'\t<hasLatexForm {_X("string")}>' +
        r"\omega(k) = 2\sqrt{D/m}\,\left|\sin\left(\frac{ka}{2}\right)\right|" +
        "</hasLatexForm>",
    f'\t<hasSymPyForm {_X("string")}>Eq(omega, 2*sqrt(D)*Abs(sin(a*k/2))/sqrt(m))</hasSymPyForm>',
    "\t<rdfs:comment>Phonon dispersion (monatomic-chain form): the textbook "
    "form of the finite-displacement frequencies the phonopy.fleur route "
    "computes (prop_phonon_spectrum). The supercell force constants D "
    "come from eq_hellmann_feynman at displaced geometries.</rdfs:comment>",
    "</rdf:Description>",
    # --- Mott Seebeck ------------------------------------------------------------
    f'<rdf:Description rdf:about="{_A("eq_seebeck_mott")}">',
    f'\t<rdf:type rdf:resource="{_A("PhysicalEquation")}"/>',
    f'\t<derivesFrom rdf:resource="{_A("eq_kohn_sham")}"/>',
    f'\t<hasDerivationLevel {_X("string")}>approximate</hasDerivationLevel>',
    f'\t<hasLatexForm {_X("string")}>' +
        r"S = -\frac{\pi^2 k_B^2 T}{3e}"
        r"\frac{d\ln\sigma(\varepsilon)}{d\varepsilon}\Big|_{\varepsilon_F}" +
        "</hasLatexForm>",
    f'\t<hasSymPyForm {_X("string")}>'
    "Eq(S, -3.96583751701583e-28*pi**2*T*Derivative(log(sigma_epsilon), epsilon))"
    "</hasSymPyForm>",
    "\t<rdfs:comment>Mott-form Seebeck: the degenerate-limit transport "
    "coefficient from the Kohn-Sham band structure (fleur.dos_seebeck; "
    "prop_seebeck).</rdfs:comment>",
    "</rdf:Description>",
    # --- bindings to the executable learned workflows --------------------------
    f'<rdf:Description rdf:about="{_A("eq_birch_murnaghan")}">',
    f'\t<computedBy rdf:resource="{_A("wf_fleur_eos")}"/>',
    "</rdf:Description>",
    f'<rdf:Description rdf:about="{_A("eq_mae_scan")}">',
    f'\t<computedBy rdf:resource="{_A("wf_fleur_mae")}"/>',
    "</rdf:Description>",
    f'<rdf:Description rdf:about="{_A("eq_phonon_dispersion")}">',
    f'\t<computedBy rdf:resource="{_A("wf_fleur_phonon")}"/>',
    "</rdf:Description>",
    f'<rdf:Description rdf:about="{_A("eq_seebeck_mott")}">',
    f'\t<computedBy rdf:resource="{_A("wf_fleur_seebeck")}"/>',
    "</rdf:Description>",
    f'<rdf:Description rdf:about="{_A("eq_hellmann_feynman")}">',
    f'\t<computedBy rdf:resource="{_A("wf_fleur_forces")}"/>',
    "</rdf:Description>",
]