#!/usr/bin/env python3
"""
Generate the aiida-reharness extension ontology (RDF/XML) on top of the
MPDS materials ontology.

Grounded in the collected operational experience (the mpds-aiida pitfall
taxonomy, 44+ entries) and the aiida-reharness project ideas:

  Layer 1  computation   engines, nodes, channels, exit codes, mixing schemes
  Layer 2  campaign      plans as individuals, PRD gate, detection classes
                         with hasValue mitigation gates (consistency-checked)
  Layer 3  experience    the pitfall corpus as classifiable individuals:
                         signature -> failure mode -> fix + FSM routing

Design rules (from aiida-reharness / reharness theory):
  - additive-only: the base ontology is imported, never modified
  - fail-loud gates: a plan that misses a required mitigation is
    INCONSISTENT, not merely unclassified (the reasoner enforces the rule)
  - physics vs infra failure modes are DISJOINT (pitfall 42: a uniform batch
    of fast 412s is infra, not physics -- never tune SCF in response)
  - routing maps onto reharness FSM state kinds: code / agent / approval /
    wait (decisions belong to states, never to runtime glue)
  - closed-world plan booleans: the plan builder asserts every mitigation
    boolean explicitly; the validator fails loud on a missing assertion

Zero non-stdlib dependencies (pure text emission; validation uses pyfactxx).
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'aiida_reharness.rdf')

BASE = "http://www.semanticweb.org/ivan/ontologies/2024/0/ontomat#"
ARH = "https://mpds.io/ontology#"
XSD = "http://www.w3.org/2001/XMLSchema#"

parts = []
w = parts.append


def esc(s):
    return (s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            .replace('"', '&quot;'))


def X(t):
    return f'rdf:datatype="{XSD}{t}"'


def cls(name, parent=None, comment=None, body=''):
    w(f'<owl:Class rdf:about="{ARH}{name}">')
    if parent:
        w(f'\t<rdfs:subClassOf rdf:resource="{ARH}{parent}"/>')
    if comment:
        w(f'\t<rdfs:comment>{esc(comment)}</rdfs:comment>')
    if body:
        w(body)
    w('</owl:Class>')


def disjoint_pairs(*pairs):
    for a, b in pairs:
        w(f'<rdf:Description rdf:about="{ARH}{a}">')
        w(f'\t<owl:disjointWith rdf:resource="{ARH}{b}"/>')
        w('</rdf:Description>')


def all_disjoint(*names):
    # NOTE: owl:AllDisjointClasses is NOT supported by the km (Kobayashi-MaRust)
    # RDF mapper — emit pairwise owl:disjointWith instead (logically equivalent,
    # quadratic in group size; our groups are tiny). FaCT++ handles both forms.
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            disjoint_pairs((names[i], names[j]))


def hv_data_sub(prop, value, xtype='boolean'):
    """subClassOf a hasValue restriction on a DATATYPE property."""
    return (f'\t<rdfs:subClassOf>\n\t\t<owl:Restriction>\n'
            f'\t\t<owl:onProperty rdf:resource="{ARH}{prop}"/>\n'
            f'\t\t<owl:hasValue {X(xtype)}>{esc(value)}</owl:hasValue>\n'
            f'\t</owl:Restriction>\n\t</rdfs:subClassOf>')


def equiv_intersection(name, conjuncts, comment=None, parent=None, gates=()):
    """name ≡ intersectionOf(conjuncts), ⊑ parent, ⊑ gates.

    conjuncts: class names or ('prop', 'someValuesFrom'|'allValuesFrom'|'hasValue', 'filler')
    restriction tuples (object properties), or ('prop', 'dhasValue', value, xtype).

    gates: (prop, value, xtype) tuples -> additional rdfs:subClassOf hasValue
    restrictions on DATATYPE properties: the fail-loud consistency gates
    (an individual classified here MUST assert the gate boolean true)."""
    w(f'<owl:Class rdf:about="{ARH}{name}">')
    if parent:
        w(f'\t<rdfs:subClassOf rdf:resource="{ARH}{parent}"/>')
    if comment:
        w(f'\t<rdfs:comment>{esc(comment)}</rdfs:comment>')
    for prop, value, xtype in gates:
        w('\t<rdfs:subClassOf>')
        w('\t\t<owl:Restriction>')
        w(f'\t\t\t<owl:onProperty rdf:resource="{ARH}{prop}"/>')
        w(f'\t\t\t<owl:hasValue {X(xtype)}>{esc(value)}</owl:hasValue>')
        w('\t\t</owl:Restriction>')
        w('\t</rdfs:subClassOf>')
    w('\t<owl:equivalentClass>')
    w('\t\t<owl:Class>')
    w('\t\t\t<owl:intersectionOf rdf:parseType="Collection">')
    for c in conjuncts:
        if isinstance(c, tuple):
            prop, kind = c[0], c[1]
            if kind == 'dhasValue':
                val, xtype = c[2], c[3]
                w('\t\t\t\t<owl:Restriction>')
                w(f'\t\t\t\t\t<owl:onProperty rdf:resource="{ARH}{prop}"/>')
                w(f'\t\t\t\t\t<owl:hasValue {X(xtype)}>{esc(val)}</owl:hasValue>')
                w('\t\t\t\t</owl:Restriction>')
            elif kind == 'hasValue':
                w('\t\t\t\t<owl:Restriction>')
                w(f'\t\t\t\t\t<owl:onProperty rdf:resource="{ARH}{prop}"/>')
                w(f'\t\t\t\t\t<owl:hasValue rdf:resource="{ARH}{c[2]}"/>')
                w('\t\t\t\t</owl:Restriction>')
            else:  # someValuesFrom / allValuesFrom
                w('\t\t\t\t<owl:Restriction>')
                w(f'\t\t\t\t\t<owl:onProperty rdf:resource="{ARH}{prop}"/>')
                w(f'\t\t\t\t\t<owl:{kind} rdf:resource="{ARH}{c[2]}"/>')
                w('\t\t\t\t</owl:Restriction>')
        else:
            w(f'\t\t\t\t<owl:Class rdf:about="{ARH}{c}"/>')
    w('\t\t\t</owl:intersectionOf>')
    w('\t\t</owl:Class>')
    w('\t</owl:equivalentClass>')
    w('</owl:Class>')


def oprop(name, domain=None, range_=None, comment=None, parents=()):
    w(f'<owl:ObjectProperty rdf:about="{ARH}{name}">')
    for p in parents:
        w(f'\t<rdfs:subPropertyOf rdf:resource="{ARH}{p}"/>')
    if domain:
        w(f'\t<rdfs:domain rdf:resource="{ARH}{domain}"/>')
    if range_:
        w(f'\t<rdfs:range rdf:resource="{ARH}{range_}"/>')
    if comment:
        w(f'\t<rdfs:comment>{esc(comment)}</rdfs:comment>')
    w('</owl:ObjectProperty>')


def dprop(name, domain, xtype, comment=None, parents=(), functional=False):
    w(f'<owl:DatatypeProperty rdf:about="{ARH}{name}">')
    if functional:
        w('\t<rdf:type rdf:resource="http://www.w3.org/2002/07/owl#FunctionalProperty"/>')
    for p in parents:
        w(f'\t<rdfs:subPropertyOf rdf:resource="{ARH}{p}"/>')
    w(f'\t<rdfs:domain rdf:resource="{ARH}{domain}"/>')
    w(f'\t<rdfs:range rdf:resource="{XSD}{xtype}"/>')
    if comment:
        w(f'\t<rdfs:comment>{esc(comment)}</rdfs:comment>')
    w('</owl:DatatypeProperty>')


def ind(name, types, props=None, comment=None):
    """props: list of ('obj', prop, value) or ('data', prop, value, xtype)."""
    w(f'<rdf:Description rdf:about="{ARH}{name}">')
    for t in types:
        w(f'\t<rdf:type rdf:resource="{ARH}{t}"/>')
    if comment:
        w(f'\t<rdfs:comment>{esc(comment)}</rdfs:comment>')
    for p in (props or []):
        if p[0] == 'obj':
            w(f'\t<{p[1]} rdf:resource="{ARH}{p[2]}"/>')
        else:
            w(f'\t<{p[1]} {X(p[3])}>{esc(p[2])}</{p[1]}>')
    w('</rdf:Description>')


def base_ind(name, types, props=None, comment=None):
    """Assert types/props about a BASE-namespace individual (additive)."""
    w(f'<rdf:Description rdf:about="{BASE}{name}">')
    for t in types:
        w(f'\t<rdf:type rdf:resource="{ARH}{t}"/>')
    if comment:
        w(f'\t<rdfs:comment>{esc(comment)}</rdfs:comment>')
    for p in (props or []):
        if p[0] == 'obj':
            w(f'\t<{p[1]} rdf:resource="{ARH}{p[2]}"/>')
        else:
            w(f'\t<{p[1]} {X(p[3])}>{esc(p[2])}</{p[1]}>')
    w('</rdf:Description>')


# ============================================================================
w('<?xml version="1.0" encoding="UTF-8"?>')
w('<rdf:RDF')
w(f'\txmlns="{ARH}"')
w('\txmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"')
w('\txmlns:owl="http://www.w3.org/2002/07/owl#"')
w('\txmlns:xml="http://www.w3.org/XML/1998/namespace"')
w(f'\txmlns:xsd="{XSD}"')  # XSD namespace (with # — XSD[:-1] dropped it)
w('\txmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#"')
w('>')

w('<owl:Ontology rdf:about="https://mpds.io/ontology.rdf">')
w('\t<rdfs:comment>aiida-reharness extension for the MPDS materials ontology: computation, campaign-plan and experience layers. Additive-only over the base; generated by gen_aiida_reharness.py.</rdfs:comment>')
w(f'\t<owl:imports rdf:resource="{BASE[:-1]}"/>')
w('</owl:Ontology>')

# =========================================================================
w('<!-- ================= LAYER 1: COMPUTATION TBox ===================== -->')

cls('ComputationalArtefact',
    comment='Root of the aiida-reharness computation layer. Additive over the base materials ontology.')

cls('DFTSystem', 'ComputationalArtefact',
    'A concrete material system submitted to an ab-initio campaign. The unit of serial one-system-at-a-time campaigns.')
cls('CalculationTask', 'ComputationalArtefact',
    'One engine run (SCF, geometry optimization, phonons). Maps to an AiiDA CalcJob or a direct yascheduler task.')
cls('Engine', 'ComputationalArtefact', 'An ab-initio code.')
cls('FLEUR', 'Engine', 'FLEUR MaX 6.2. Only Anderson and straight mixing are implemented in this build.')
cls('CRYSTAL', 'Engine', 'CRYSTAL23 public (Pcrystal MPI binary).')
cls('Inpgen', 'Engine', 'FLEUR input generator.')
cls('LLMEngine', 'Engine',
    'A self-hosted LLM used as a zero-external-cost reasoning assistant for ontology '
    'tasks (axiom help, unmatched-failure diagnosis). Not a DFT engine.')

# Engine individuals named after the yascheduler engine config keys
# ([engine.fleur], [engine.pcrystal]) so plans speak yascheduler's language.
ind('fleur', ['FLEUR'],
    [('data', 'hasYaschedulerKey', 'fleur', 'string')],
    comment='The [engine.fleur] yascheduler engine: FLEUR MaX 6.2, platforms linux darwin.')
ind('pcrystal', ['CRYSTAL'],
    [('data', 'hasYaschedulerKey', 'pcrystal', 'string')],
    comment='The [engine.pcrystal] yascheduler engine: Pcrystal MPI binary, CRYSTAL23.')
ind('inpgen', ['Inpgen'], comment='inpgen input generator (lattice -> inp.xml).')
ind('qwen', ['LLMEngine'],
    [('data', 'hasModelId', 'qwen/qwen3.8-27b', 'string'),
     ('data', 'hasEndpoint', 'http://afghani-578.local:1234/v1', 'string')],
    comment="The Mac's self-hosted LM Studio LLM (afghani-578.local, OpenAI-compatible "
           'API). Assistance with ontology: axiom authoring help, diagnosis of failures '
           'that match no experience signature. Zero external API cost.')
all_disjoint('fleur', 'pcrystal', 'inpgen', 'qwen')

# Data properties for engine metadata
dprop('hasYaschedulerKey', 'Engine', 'string',
      'The yascheduler engine config section key ([engine.<key>]).')
dprop('hasModelId', 'LLMEngine', 'string', 'Model id at the OpenAI-compatible endpoint.')
dprop('hasEndpoint', 'LLMEngine', 'string', 'Base URL of the OpenAI-compatible endpoint.')

cls('ComputeNode', 'ComputationalArtefact', 'A machine registered in yascheduler_nodes.')
cls('HomeServerNode', 'ComputeNode', 'Ubuntu home server, 16 physical cores, local yascheduler node.')
cls('VultrBareMetalNode', 'ComputeNode', 'vbm-24c-256gb-amd EPYC bare-metal (policy: max 1BM+1VM).')
cls('MacNode', 'ComputeNode', 'Afghani-578.local arm64. Wi-Fi only, sleeps without caffeinate, DHCP address.')
cls('HetznerNode', 'ComputeNode', 'VPS with intermittent SSH drops: premature DONE, truncated out.xml.')
ind('home_server', ['HomeServerNode'])
ind('vultr_bm', ['VultrBareMetalNode'])
ind('mac_node', ['MacNode'])
all_disjoint('HomeServerNode', 'VultrBareMetalNode', 'MacNode', 'HetznerNode')

cls('Platform', 'ComputationalArtefact', 'OS platform of a compute node.')
ind('linux', ['Platform'])
ind('darwin', ['Platform'])
all_disjoint('linux', 'darwin')

cls('SubmitChannel', 'ComputationalArtefact',
    'How a task reaches the engine: AiiDA workchain (provenance-tracked) or direct yascheduler API.')
cls('AiiDAWorkChain', 'SubmitChannel', 'fleur.mpds / crystal.mpds / CDGFleurSCFOptimizer via the yascheduler computer. Provenance, caching, restart.')
cls('DirectYaschedulerAPI', 'SubmitChannel', 'queue_submit_task bypassing AiiDA. No provenance; used for resubmits and tests.')
all_disjoint('AiiDAWorkChain', 'DirectYaschedulerAPI')

cls('FsmLayer', 'ComputationalArtefact',
    'The aiida-reharness time-scale split: which layer owns a decision.')
cls('OrchestrationLayer', 'FsmLayer', 'reharness FSM: code/agent leaves, wait states, guards, approval gates. Event-scale.')
cls('ComputeLayer', 'FsmLayer', 'AiiDA daemon: CalcJobs/WorkChains. Days-scale, provenance-tracked.')
cls('ReasoningLayer', 'FsmLayer', 'pyfactxx ontology classification: plan validation at compile time, diagnosis at runtime. Zero tokens.')
all_disjoint('OrchestrationLayer', 'ComputeLayer', 'ReasoningLayer')

cls('AiiDAExitCodeFamily', 'ComputationalArtefact', 'Exit-code family of a finished process (dft.mpds.io listing convention).')
ind('exit_0', ['AiiDAExitCodeFamily'], comment='Success.')
ind('exit_303', ['AiiDAExitCodeFamily'], comment='SCF did not converge OR retrieved folder lacks out.xml (pitfall 39: check for SSH-drop DONE-marking).')
ind('exit_3xx', ['AiiDAExitCodeFamily'], comment='Other FLEUR workchain exits: 300/301 fleur.base general, 360 elastic stage.')
ind('exit_362', ['AiiDAExitCodeFamily'], comment='ERROR_DID_NOT_CONVERGE: SCF ran full iterations without converging. Physics, not infra.')
ind('exit_412', ['AiiDAExitCodeFamily'], comment='fleur.mpds top-level: SCF converged but downstream property calc not triggered.')
ind('exit_497', ['AiiDAExitCodeFamily'], comment='CDGFleurSCFOptimizer: SCF converged but lattice optimization incomplete.')
ind('exit_5xx', ['AiiDAExitCodeFamily'], comment='Infra failures, empty reason string in the dft.mpds.io listing.')
all_disjoint('exit_0', 'exit_303', 'exit_3xx', 'exit_362', 'exit_412', 'exit_497', 'exit_5xx')

cls('MixingScheme', 'ComputationalArtefact', 'FLEUR SCF charge-density mixing (InputSchema 0.37).')
ind('Anderson', ['MixingScheme'], comment='Default choice: alpha 0.15 converges NiZn in 17 iterations (pitfall 22b).')
ind('Straight', ['MixingScheme'], comment='Too conservative for hard systems: stuck at 40-260 Htr distances (pitfalls 22b, 42).')
ind('Broyden1', ['MixingScheme'], comment='NOT implemented in the FLEUR 6.2 build on the compute nodes (pitfall 15).')
ind('Broyden2', ['MixingScheme'], comment='NOT implemented in the FLEUR 6.2 build (pitfall 15).')
all_disjoint('Anderson', 'Straight', 'Broyden1', 'Broyden2')

# ---------------------------------------------------------------------------
w('<!-- Computation layer properties -->')
oprop('hasEngine', 'CalculationTask', 'Engine', 'Engine that runs the task.')
oprop('runsOn', 'CalculationTask', 'ComputeNode', 'yascheduler node the task deploys to.')
oprop('hasSubmitChannel', 'CalculationTask', 'SubmitChannel', 'AiiDA workchain vs direct API (pitfalls 17/18).')
oprop('hasExitCodeFamily', 'CalculationTask', 'AiiDAExitCodeFamily', 'Derived exit-code family.')
oprop('hasMixingScheme', 'CalculationTask', 'MixingScheme', 'SCF mixing scheme of the task.')
oprop('hasElement', 'DFTSystem', None,
       comment='Elements in the system. Range = the base ChemicalElement class. '
               'NOTE: deliberately NOT rdfs:subPropertyOf hasChemicalElements — km (Kobayashi-MaRust) '
               'has no subPropertyOf mapping; the range declaration carries the semantics.')
w(f'<owl:ObjectProperty rdf:about="{ARH}hasElement">')
w(f'\t<rdfs:range rdf:resource="{BASE}ChemicalElement"/>')
w('</owl:ObjectProperty>')
oprop('hasFailureMode', 'CalculationTask', 'EngineFailureMode')

# =========================================================================
w('<!-- ================= LAYER 2: CAMPAIGN PLANS ======================= -->')

cls('CampaignPlan', 'ComputationalArtefact',
    'A compiled aiida-reharness campaign: systems, tasks, execution rules. The subject of the PRD gate.')
cls('Observation', 'ComputationalArtefact',
    'A runtime observation asserted for diagnosis: exit code, output signature, elements seen.')

# execution mode: the serial-campaign preference, as a classifiable value
cls('ExecutionMode', 'ComputationalArtefact', 'How the campaign driver schedules systems.')
ind('serial', ['ExecutionMode'], comment='One system at a time, one engine owning all cores. House preference for DFT campaigns.')
ind('batch', ['ExecutionMode'], comment='Concurrent submissions. OpenMPI resource exhaustion risk on small nodes (pitfall 20).')
all_disjoint('serial', 'batch')

w('<!-- Plan properties -->')
oprop('hasSystem', 'CampaignPlan', 'DFTSystem')
oprop('hasTask', 'CampaignPlan', 'CalculationTask')
oprop('hasExecutionMode', 'CampaignPlan', 'ExecutionMode')
dprop('prdApproved', 'CampaignPlan', 'boolean',
      'The reharness PRD gate: the human approves the intent (PRD), never the FSM graph. '
      'Asserted true only after the human approved the PRD.', functional=True)
dprop('hasMitigationJUDFTWarnOnly', 'CalculationTask', 'boolean',
      'JUDFT_WARN_ONLY staged before the engine run (pitfalls 8c/32: heavy elements abort with '
      '"Too low eigenvalue detected" without it). AiiDA stages it automatically; direct API must put '
      'touch JUDFT_WARN_ONLY in the spawn command.', functional=True)
dprop('hasMitigationSphereCaps', 'CalculationTask', 'boolean',
      'Per-system MT-sphere radius caps applied via set_species (pitfall 37: inpgen auto-assigns '
      'large spheres to heavy 6s cations; differ 2 aborts at setup).', functional=True)
dprop('hasPerSystemTemplates', 'CalculationTask', 'boolean',
      'Species-level edits live in per-system templates, never in shared base templates (pitfall 38).', functional=True)
dprop('hasSpawnNohup', 'CalculationTask', 'boolean',
      'nohup present in the yascheduler spawn command (pitfall 31: run_bg kills the engine when the '
      'SSH poll cycle reaps the channel; symptom: 1-3 iterations then truncated out.xml).', functional=True)
dprop('hasBatchEvalExitZero', 'CampaignPlan', 'boolean',
      'True when every evaluator CalcJob in the observed batch finished exit 0 (pitfall 42-BSD: '
      'uniform fast 412s with clean evals = infra signature, not physics).', functional=True)
dprop('hasSignatureText', 'Observation', 'string',
      'Raw failure text (engine error line, parser message, log line) asserted for diagnosis.')

# ---------------------------------------------------------------------------
w('<!-- Element typing (additive over base individuals) -->')
cls('HeavyElement', None,
    'f-electron elements: lanthanides + actinides. Ghost states (JUDFT_WARN_ONLY), '
    '4f occupation fluctuation is normal (pitfalls 8c, 9).')
cls('LargeMTSphereElement', None,
    'Cations with inpgen-auto large MT spheres (2.7-2.8 bohr): high-n s valence states cannot '
    'confine; differ 2 at setup (pitfall 37).')
for e in ['La', 'Ce', 'Pr', 'Nd', 'Pm', 'Sm', 'Eu', 'Gd', 'Tb', 'Dy', 'Ho',
          'Er', 'Tm', 'Yb', 'Lu', 'Ac', 'Th', 'Pa', 'U', 'Np', 'Pu', 'Am',
          'Cm', 'Bk', 'Cf', 'Es', 'Fm', 'Md', 'No', 'Lr']:
    base_ind(e, ['HeavyElement'])
for e in ['Ba', 'Cs', 'Rb', 'K']:
    base_ind(e, ['LargeMTSphereElement'])

# ---------------------------------------------------------------------------
w('<!-- Detection classes: what the reasoner infers from a plan -->')

equiv_intersection('FElementSystem', [
    'DFTSystem',
    ('hasElement', 'someValuesFrom', 'HeavyElement'),
], parent='DFTSystem',
    comment='A system containing at least one f-element (lanthanide/actinide): JUDFT_WARN_ONLY '
            'required, 4f occupation fluctuation in SCF is normal (pitfalls 8c, 9).')

equiv_intersection('LargeSphereCationSystem', [
    'DFTSystem',
    ('hasElement', 'someValuesFrom', 'LargeMTSphereElement'),
], parent='DFTSystem',
    comment='A system containing Ba/Cs/Rb/K: inpgen auto-assigns large MT spheres, differ 2 at '
            'setup without per-system sphere caps (pitfall 37).')

# Mitigation-required classes on tasks: the CONSISTENCY GATES.
# A task classified into one of these MUST assert the mitigation boolean true,
# otherwise the KB is inconsistent -> caught at compile time, fail-loud.

equiv_intersection('NeedsJUDFTWarnOnly', [
    'CalculationTask',
    ('hasSystem', 'someValuesFrom', 'FElementSystem'),
], parent='CalculationTask',
    gates=[('hasMitigationJUDFTWarnOnly', 'true', 'boolean')],
    comment='Task over an f-element system: JUDFT_WARN_ONLY is REQUIRED (pitfall 8c). '
            'Gate: hasMitigationJUDFTWarnOnly must be true, else INCONSISTENT.')

equiv_intersection('NeedsSphereCaps', [
    'CalculationTask',
    ('hasSystem', 'someValuesFrom', 'LargeSphereCationSystem'),
], parent='CalculationTask',
    gates=[('hasMitigationSphereCaps', 'true', 'boolean'),
           ('hasPerSystemTemplates', 'true', 'boolean')],
    comment='Task over a Ba/Cs/Rb/K system: per-system MT-sphere caps REQUIRED (pitfall 37). '
            'Gates: hasMitigationSphereCaps AND hasPerSystemTemplates must both be true.')

equiv_intersection('DirectFLEURSubmit', [
    'CalculationTask',
    ('hasEngine', 'hasValue', 'fleur'),
    ('hasSubmitChannel', 'hasValue', 'DirectYaschedulerAPI'),
], parent='CalculationTask',
    gates=[('hasSpawnNohup', 'true', 'boolean'),
           ('hasMitigationJUDFTWarnOnly', 'true', 'boolean')],
    comment='FLEUR task on the direct yascheduler API (no AiiDA staging): spawn must carry '
            'nohup and JUDFT_WARN_ONLY itself (pitfalls 31, 32). Gates: hasSpawnNohup AND '
            'hasMitigationJUDFTWarnOnly must both be true.')

# Detection-only classes (flagged, not fatal): wrong parameter choices.
cls('BroydenOnFLEUR62', 'CalculationTask',
    'Broyden1/2 mixing requested on the FLEUR 6.2 build: NOT implemented, the engine errors '
    'at startup (pitfall 15). Flagged by classification.')
equiv_intersection('BroydenOnFLEUR62', [
    'CalculationTask',
    ('hasMixingScheme', 'hasValue', 'Broyden1'),
])
cls('Broyden2OnFLEUR62', 'CalculationTask',
    'Same trap with Broyden2 (pitfall 15).')
equiv_intersection('Broyden2OnFLEUR62', [
    'CalculationTask',
    ('hasMixingScheme', 'hasValue', 'Broyden2'),
])

cls('PRDApprovedPlan', 'CampaignPlan',
    'A plan whose PRD the human approved. The only plan a run may start (reharness: '
    'the human approves the intent, never the graph).',
    body=hv_data_sub('prdApproved', 'true'))

# Infra signature: uniform fast 412s with clean evaluator exit codes (pitfall 42-BSD).
equiv_intersection('InfraSignatureBatch', [
    'CampaignPlan',
    ('hasTask', 'someValuesFrom', 'TaskExit412'),
    ('hasAllTasksExit412', 'dhasValue', 'true', 'boolean'),
    ('hasBatchEvalExitZero', 'dhasValue', 'true', 'boolean'),
], parent='CampaignPlan',
    comment='A fast uniform 412 batch with every evaluator CalcJob at exit 0: infrastructure '
            'failure signature (pitfall 42). Never tune SCF parameters in response. '
            'hasAllTasksExit412 is a closed-world builder assertion (FaCT++ cannot classify '
            'into forall-defined classes).')
cls('AllTasksExit412', 'CampaignPlan',
    'DEPRECATED indirection: FaCT++ realisation does not classify instances into '
    'forall-defined classes (verified empirically), so this class carries no equivalentClass '
    'axiom. The all-tasks-exit-412 check is a plan-bUILDER assertion (hasAllTasksExit412), '
    'asserted closed-world from the observed task states.')
dprop('hasAllTasksExit412', 'CampaignPlan', 'boolean',
      'Closed-world plan-builder assertion: every task in the plan observed at exit family 412. '
      'Computed by the validator from task states, not inferred by the reasoner '
      '(FaCT++ cannot classify into forall-defined classes).',
      parents=(), functional=True)
cls('TaskExit412', 'CalculationTask',
    'A task whose observed exit-code family is 412.')
equiv_intersection('TaskExit412', [
    'CalculationTask',
    ('hasExitCodeFamily', 'hasValue', 'exit_412'),
])

# =========================================================================
w('<!-- ================= LAYER 3: EXPERIENCE (pitfall corpus) =========== -->')

cls('EngineFailureMode', 'ComputationalArtefact',
    'A class of engine failures with known detection, cause and fix.')
cls('InfraFailureMode', 'EngineFailureMode',
    'Infrastructure failures: SSH drops, zombie processes, occupancy-poll bugs, spawn-channel '
    'hangup. Fix infrastructure; NEVER answer with SCF parameter tuning.')
cls('PhysicsFailureMode', 'EngineFailureMode',
    'Physics-level failures: convergence, ghost states, MT-sphere confinement, basis set.')
disjoint_pairs(('InfraFailureMode', 'PhysicsFailureMode'))
cls('ConvergenceFailureMode', 'PhysicsFailureMode', 'SCF/geometry convergence.')
cls('BasisSetFailureMode', 'PhysicsFailureMode',
    'Basis-set problems: non-neutral cell, linear dependence, neighbor-list limits.')
cls('InputPrepFailureMode', 'PhysicsFailureMode',
    'Input-generation errors: XIncludes, latsys, primitive-vs-conventional cell.')
disjoint_pairs(('ConvergenceFailureMode', 'BasisSetFailureMode'))
disjoint_pairs(('ConvergenceFailureMode', 'InputPrepFailureMode'))
disjoint_pairs(('BasisSetFailureMode', 'InputPrepFailureMode'))
cls('DiagnosticsGap', 'EngineFailureMode',
    'Failure modes with signature ambiguity: must cross-reference BOTH databases and read '
    'output files before routing (pitfall 24: DONE does not mean succeeded, at either layer).')

cls('FsmStateKind', 'ComputationalArtefact',
    'reharness FSM state kinds: where a fix routes. Decisions belong to FSM states, never '
    'to imperative runtime glue.')
ind('codeState', ['FsmStateKind'], comment='Deterministic code leaf: run the fix command, no tokens.')
ind('agentState', ['FsmStateKind'], comment='LLM judgment leaf: novel diagnosis, input authoring.')
ind('approvalState', ['FsmStateKind'], comment='Human approval gate: risky or policy-gated actions.')
ind('waitState', ['FsmStateKind'], comment='Poll an external signal: daemon process, yascheduler DB, output file.')
all_disjoint('codeState', 'agentState', 'approvalState', 'waitState')

w('<!-- Experience properties -->')
oprop('hasRouting', 'EngineFailureMode', 'FsmStateKind',
      'Where the FSM routes a failure of this mode: code / agent / approval / wait.')
oprop('hasObservedExitCode', 'EngineFailureMode', 'AiiDAExitCodeFamily',
      'Exit-code family typically observed for this failure mode.')
oprop('hasDetectedClass', 'EngineFailureMode', None,
      'The plan-level detection class that flags this failure mode pre-emptively (range: the '
      'detection classes above).')
dprop('hasPitfallRef', 'EngineFailureMode', 'string',
      'Pitfall identifier in the collected experience (mpds-aiida skill taxonomy), e.g. 8c, 22b, 42-BSD.')
dprop('hasSignature', 'EngineFailureMode', 'string',
      'Deterministic signature regexes (Python re syntax) matched against failure text.')
dprop('hasFix', 'EngineFailureMode', 'string',
      'The known fix: exact command or action, from the collected experience.')
dprop('hasEvidenceCommand', 'EngineFailureMode', 'string',
      'Deterministic evidence-gathering command to run before concluding the mode.')

w('<!-- The pitfall individuals -->')

ind('pf_ghost_states', ['ConvergenceFailureMode', 'PhysicsFailureMode'],
    [('obj', 'hasRouting', 'codeState'),
     ('obj', 'hasObservedExitCode', 'exit_303'),
     ('obj', 'hasDetectedClass', 'NeedsJUDFTWarnOnly'),
     ('data', 'hasPitfallRef', '8c', 'string'),
     ('data', 'hasSignature', r'Too low eigenvalue detected', 'string'),
     ('data', 'hasFix', 'Stage JUDFT_WARN_ONLY in the task dir before the engine run. '
      'AiiDA FleurCalculation stages it automatically (line 465-468 of calculation.fleur); '
      'direct yascheduler API must have touch JUDFT_WARN_ONLY in the spawn command.', 'string')],
    'Ghost states from core electrons of f-elements abort the run. Warning escalated to fatal by default.')

ind('pf_mt_sphere_confinement', ['BasisSetFailureMode', 'PhysicsFailureMode'],
    [('obj', 'hasRouting', 'agentState'),
     ('obj', 'hasObservedExitCode', 'exit_303'),
     ('obj', 'hasDetectedClass', 'NeedsSphereCaps'),
     ('data', 'hasPitfallRef', '37', 'string'),
     ('data', 'hasSignature', r'differ 2: problems with solving dirac equation', 'string'),
     ('data', 'hasSignature', r'too few nodes', 'string'),
     ('data', 'hasFix', 'Per-system MT-sphere radius caps via set_species (masci_tools): '
      'use EXACT species names from that system inp.xml (e.g. "Barium (Ba)"); caps live in '
      'per-system templates only, never shared base templates. Diagnose the failing species '
      'from the FLEUR "out" file, not from expectation.', 'string')],
    'High-n s valence states cannot confine in inpgen-auto large MT spheres of Ba/Cs/Rb/K. '
    'Dominant mode behind dft.mpds.io geometry-optimization failures.')

ind('pf_broyden_not_implemented', ['InputPrepFailureMode', 'PhysicsFailureMode'],
    [('obj', 'hasRouting', 'codeState'),
     ('obj', 'hasDetectedClass', 'BroydenOnFLEUR62'),
     ('data', 'hasPitfallRef', '15', 'string'),
     ('data', 'hasSignature', r'Broyden 1/2 method not implemented', 'string'),
     ('data', 'hasFix', 'Use Anderson mixing alpha=0.15 (or straight as last resort). '
      'Broyden1/Broyden2 are NOT implemented in the FLEUR 6.2 build.', 'string')],
    'The InputSchema lists Broyden1/2 as valid imix values but the build errors at startup.')

ind('pf_straight_too_conservative', ['ConvergenceFailureMode', 'PhysicsFailureMode'],
    [('obj', 'hasRouting', 'agentState'),
     ('obj', 'hasObservedExitCode', 'exit_362'),
     ('data', 'hasPitfallRef', '22b', 'string'),
     ('data', 'hasSignature', r'DID_NOT_CONVERGE', 'string'),
     ('data', 'hasFix', 'Anderson alpha=0.15 (OLD scheme) converges NiZn in 17 iterations; '
      'straight alpha=0.05 stuck at 40-260 Htr. Straight-mixing 2x300 does NOT rescue '
      '412/497 hard systems (attempt-2 reproduced attempt-1 exactly).', 'string')],
    'PR #20 straight-mixing scheme evaluated and REFUTED on SrTiO3/GdNi/NiZn.')

ind('pf_walltime_keyerror', ['InfraFailureMode'],
    [('obj', 'hasRouting', 'codeState'),
     ('obj', 'hasObservedExitCode', 'exit_497'),
     ('data', 'hasPitfallRef', '35', 'string'),
     ('data', 'hasSignature', r"KeyError: 'walltime'", 'string'),
     ('data', 'hasSignature', r"unsupported operand type\(s\) for -: 'NoneType' and 'NoneType'", 'string'),
     ('data', 'hasFix', 'Guard parser-derived keys: output_parameters.get("walltime", 0) at '
      'scf.py line 696, and or 0 / .get(...) at every subtraction site in get_res. Patched '
      'in installed aiida_fleur (backup at .bak).', 'string')],
    'Truncated out.xml yields partial output_parameters; bracket access Excepts the SCF workchain.')

ind('pf_truncated_outxml', ['InfraFailureMode'],
    [('obj', 'hasRouting', 'codeState'),
     ('obj', 'hasObservedExitCode', 'exit_303'),
     ('data', 'hasPitfallRef', '12', 'string'),
     ('data', 'hasSignature', r'The out.xml file is broken', 'string'),
     ('data', 'hasSignature', r'Repairing was not possible', 'string'),
     ('data', 'hasEvidenceCommand', 'sudo PGPASSWORD= /data/pg/bin/psql -h localhost -U postgres -d aiida -c "..." '
      'and yascheduler_tasks.metadata->>error for SSH failure records; compare retrieved FolderData content', 'string'),
     ('data', 'hasFix', 'Root cause chain: SSH drop mid-write (pitfall 13/39) or spawn-channel hangup '
      '(pitfall 31) -> truncated out.xml -> masci_tools first parse consumes the handle at EOF '
      '(pitfall 33: wrap in seek(0)) -> exit 303. Resubmit; check yascheduler metadata for the '
      'SSH failure before tuning anything.', 'string')],
    'Missing shell.out/out.error warnings are a RED HERRING: the parser only warns on those.')

ind('pf_premature_done', ['InfraFailureMode'],
    [('obj', 'hasRouting', 'codeState'),
     ('data', 'hasPitfallRef', '13', 'string'),
     ('data', 'hasSignature', r'no </fleurOutput> closing tag', 'string'),
     ('data', 'hasFix', 'Task marked DONE after 7-14 iterations on an SSH-unstable node. '
      'Cross-reference yascheduler_tasks.status=2 vs the AiiDA process state; resubmit; '
      'if persistent, disable the unstable node in yascheduler_nodes.', 'string')],
    'DONE does not mean succeeded at either layer (pitfall 18/24).')

ind('pf_spawn_channel_hangup', ['InfraFailureMode'],
    [('obj', 'hasRouting', 'codeState'),
     ('obj', 'hasDetectedClass', 'DirectFLEURSubmit'),
     ('data', 'hasPitfallRef', '31', 'string'),
     ('data', 'hasSignature', r'completed after 1 iterations', 'string'),
     ('data', 'hasSignature', r'truncated mid-iteration', 'string'),
     ('data', 'hasFix', 'nohup is REQUIRED in the yascheduler spawn command: run_bg creates the '
      'process on an SSH channel that is killed when the poll cycle reaps it. Never quote the '
      'live [engine.fleur] spawn from memory (pitfall 11): read it from /etc/yascheduler/yascheduler.conf.', 'string')],
    'Without nohup the engine dies after 1-3 SCF iterations; yascheduler still marks DONE.')

ind('pf_false_idle_occupancy', ['InfraFailureMode'],
    [('obj', 'hasRouting', 'codeState'),
     ('obj', 'hasDetectedClass', 'InfraSignatureBatch'),
     ('data', 'hasPitfallRef', '42', 'string'),
     ('data', 'hasSignature', r'uniform batch of fast 412s', 'string'),
     ('data', 'hasEvidenceCommand', 'Verify evals actually ran: yac task rows for the eval '
      'calcjobs + iteration count in the retrieved out file, BEFORE tuning SCF parameters', 'string'),
     ('data', 'hasFix', 'BSD ps vs GNU :255 occupancy poll bug: false-idle node polls rmtree '
      'live task dirs on Darwin; engines die silently RC=2. Fixed in installed yascheduler 1.8.1 '
      '(kit /data/fleur_campaign/patches/). A uniform fast-412 batch with eval exit 0 = infra, '
      'not physics.', 'string')],
    'THE physics-vs-infra separation rule: verify evals ran before tuning SCF parameters.')

ind('pf_unit_cell_not_neutral', ['BasisSetFailureMode', 'PhysicsFailureMode'],
    [('obj', 'hasRouting', 'agentState'),
     ('data', 'hasPitfallRef', '19', 'string'),
     ('data', 'hasSignature', r'INPBAS \*\*\*\* UNIT CELL NOT NEUTRAL', 'string'),
     ('data', 'hasFix', 'Basis set charge mismatch (MPDSBSL_NEUTRAL_6TH family): Yb-containing '
      'perovskites with certain oxidation states. Custom basis assignments or different '
      'oxidation states needed per composition.', 'string')],
    'A basis problem, not a runtime issue: the cell is fine, the assigned bases are not.')

ind('pf_wbecke_neighbor_list', ['BasisSetFailureMode', 'PhysicsFailureMode'],
    [('obj', 'hasRouting', 'agentState'),
     ('data', 'hasPitfallRef', '26', 'string'),
     ('data', 'hasSignature', r'WBECKE_F NEIGHBOR LIST TOO BIG', 'string'),
     ('data', 'hasFix', 'LIMBEK is absent from the CRYSTAL23 public build (like CYCLES: use '
      'MAXCYCLE). For covalent solids: HF has no Becke grid, but diffuse bases (pob-DZVP-rev2, '
      '6-21G*) may then hit BASIS SET LINEARLY DEPENDENT. MgO DFT-PBE works; Si diamond needs HF.', 'string')],
    'Public-keyword limitations on the Mac arm64 build.')

ind('pf_xinclude_not_flattened', ['InputPrepFailureMode', 'PhysicsFailureMode'],
    [('obj', 'hasRouting', 'codeState'),
     ('data', 'hasPitfallRef', '1', 'string'),
     ('data', 'hasSignature', r'XML document cannot be validated against Schema', 'string'),
     ('data', 'hasFix', 'inpgen emits xi:include tags (NOT self-closing: href="kpts.xml"> '
      '</xi:include>). Flatten all XIncludes into one self-contained inp.xml before submitting '
      'directly; assert len(re.findall(xi:include, inp_xml)) == 0. AiiDA FleurinpData flattens '
      'automatically.', 'string')],
    'yascheduler only ships input_files: un-flattened XIncludes reference missing files.')

ind('pf_unverified_method_claim', ['DiagnosticsGap'],
    [('obj', 'hasRouting', 'approvalState'),
     ('data', 'hasPitfallRef', '9', 'string'),
     ('data', 'hasFix', 'Do NOT claim DFT+HIA/DFT+U is required for 4f systems without testing '
      'plain PBE first. GdNi: the actual issue was itmax 50 vs 200 and wrong alpha. 4f occupation '
      'fluctuation keeping distance at 1e-3..1e-4 is NORMAL; gate on held-out accuracy, not '
      'SatAgg (single-run sat is degenerate).', 'string')],
    'Methodology gate: untested method claims route to human approval.')

ind('pf_orte_resource_exhaustion', ['InfraFailureMode'],
    [('obj', 'hasRouting', 'codeState'),
     ('data', 'hasPitfallRef', '20', 'string'),
     ('data', 'hasSignature', r'ORTE_ERROR_LOG: Out of resource', 'string'),
     ('data', 'hasSignature', r'process killed \(SIGTERM\)', 'string'),
     ('data', 'hasFix', 'Concurrent --oversubscribe Pcrystal tasks exhaust ORTE on small '
      'nodes: 17/37 crashed. Submit in batches of 5-10, match ncpus to physical cores, run '
      'campaigns serially.', 'string')],
    'Batch-vs-serial scheduling decision grounded in a measured crash rate.')

ind('pf_stale_waiting_wedge', ['InfraFailureMode'],
    [('obj', 'hasRouting', 'codeState'),
     ('obj', 'hasObservedExitCode', 'exit_412'),
     ('data', 'hasPitfallRef', '33', 'string'),
     ('data', 'hasFix', 'A stale waiting workchain of type fleur.mpds silently wedges the '
      'serial campaign driver: its submit gate counts active workchains. Clean waiting '
      'processes BEFORE launching a campaign (verdi process repair; kill remaining via '
      'ProcessNode set_exit_status(130) + seal; DROP the exit_status filter on sealed nodes).', 'string')],
    'Campaign driver precondition, checked pre-launch, not post-mortem.')

# --- north-star layer (AGENTS.md): property-driven workflow synthesis ---
from north_star import NORTH_STAR
parts.extend(NORTH_STAR)

# --- physics-derivation layer: Schroedinger root + approximation DAG ---
from physics_layer import PHYSICS_LAYER
parts.extend(PHYSICS_LAYER)

w('</rdf:RDF>')

with open(OUT, 'w') as f:
    f.write('\n'.join(parts) + '\n')
print(f'wrote {OUT} ({os.path.getsize(OUT)} bytes, {len(parts)} lines)')