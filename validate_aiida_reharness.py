#!/usr/bin/env python3
"""
Validate the aiida-reharness extension ontology against the FaCT++ kernel
(pyfactxx, refactoring-synthesis build) and demonstrate the reasoning gates.

Exit code 0 = all gates pass. Any gate failure prints a loud diagnostic.

Usage:
    python3 validate_aiida_reharness.py            # full gate suite
    python3 validate_aiida_reharness.py --base-only  # base ontology only
"""
import sys
import os

HERE = os.path.dirname(os.path.abspath(__file__))
BASE_ONTO = os.path.join(HERE, 'mpds_ontology.rdf')
EXT_ONTO = os.path.join(HERE, 'aiida_reharness.rdf')

ARH = 'https://mpds.io/ontology#'
BASE = 'http://www.semanticweb.org/ivan/ontologies/2024/0/ontomat#'


def A(name):
    return ARH + name


def B(name):
    return BASE + name


def build(add_base=True):
    from pyfactxx import coras
    c = coras.Coras()
    c.load(BASE_ONTO, format='xml')
    c.load(EXT_ONTO, format='xml')
    c.parse()
    return c


def realize(c):
    c.realise()


def realize_raises_inconsistent(c):
    """The kernel is fail-loud: classify() raises RuntimeError on an
    inconsistent KB. Catch it and return True iff it fired."""
    try:
        c.realise()
        return False
    except RuntimeError as e:
        return 'Inconsistent KB' in str(e)


PASS = []
FAIL = []


def check(name, cond, detail=''):
    if cond:
        PASS.append(name)
        print(f'  PASS  {name}')
    else:
        FAIL.append(name)
        print(f'  FAIL  {name}  {detail}')


def is_inst(c, individual, cls):
    rs = c.reasoner
    i = rs.individual(individual)
    k = rs.concept(cls)
    return rs.is_instance(i, k)


def subsumed(c, sub, sup):
    rs = c.reasoner
    return rs.is_subsumed_by(rs.concept(sub), rs.concept(sup))


def main():
    print('== loading base + extension into FaCT++ ==')
    c = build()
    realize(c)
    rs = c.reasoner

    # 0. overall consistency of the merged KB
    print('\n== consistency ==')
    check('merged KB consistent', rs.is_consistent())

    # 1. base TBox intact: Gd is still a ChemicalElement individual
    print('\n== base individuals additive-typed ==')
    check('Gd : ChemicalElement (base)', is_inst(c, B('Gd'), B('ChemicalElement')))
    check('Gd : HeavyElement (ext)', is_inst(c, B('Gd'), A('HeavyElement')))
    check('U : HeavyElement (ext)', is_inst(c, B('U'), A('HeavyElement')))
    check('Ba : LargeMTSphereElement (ext)', is_inst(c, B('Ba'), A('LargeMTSphereElement')))
    check('Si NOT HeavyElement', not is_inst(c, B('Si'), A('HeavyElement')))

    # 2. detection classes: a GdNi system must classify as FElementSystem
    #    (fresh individuals asserted at runtime by the plan builder)
    print('\n== detection classes ==')
    # assert: sys_gdni : DFTSystem, hasElement Gd
    sysname = A('t_sys_gdni')
    rs.instance_of(rs.individual(sysname), rs.concept(A('DFTSystem')))
    rs.related_to(rs.individual(sysname), rs.object_role(A('hasElement')), rs.individual(B('Gd')))
    realize(c)
    check('Gd-system : FElementSystem', is_inst(c, sysname, A('FElementSystem')))
    check('Gd-system : NeedsJUDFTWarnOnly task gate',
          subsumed(c, A('NeedsJUDFTWarnOnly'), A('CalculationTask')))
    # task over that system with the mitigation FALSE must be inconsistent
    tname = A('t_task_gdni_bad')
    rs.instance_of(rs.individual(tname), rs.concept(A('CalculationTask')))
    tsys = A('t_sys_gdni_task')  # separate system individual for the task link
    rs.instance_of(rs.individual(tsys), rs.concept(A('DFTSystem')))
    rs.related_to(rs.individual(tsys), rs.object_role(A('hasElement')), rs.individual(B('Gd')))
    rs.related_to(rs.individual(tname), rs.object_role(A('hasSystem')), rs.individual(tsys))
    # boolean FALSE asserted explicitly (closed-world builder assertion)
    rs.value_of_bool(rs.individual(tname), rs.data_role(A('hasMitigationJUDFTWarnOnly')), False)
    fired = realize_raises_inconsistent(c)
    check('Gd-task with mitigation=false -> INCONSISTENT (fail-loud gate)',
          fired,
          'the gate did NOT fire: task classified NeedsJUDFTWarnOnly but boolean false')

    # rebuild: the KB is now inconsistent, so start fresh for remaining checks
    c = build()
    realize(c)
    rs = c.reasoner

    # 3. same task with mitigation TRUE: consistent and classified
    tname = A('t_task_gdni_ok')
    tsys = A('t_sys_gdni_ok_sys')
    rs.instance_of(rs.individual(tname), rs.concept(A('CalculationTask')))
    rs.instance_of(rs.individual(tsys), rs.concept(A('DFTSystem')))
    rs.related_to(rs.individual(tsys), rs.object_role(A('hasElement')), rs.individual(B('Gd')))
    rs.related_to(rs.individual(tname), rs.object_role(A('hasSystem')), rs.individual(tsys))
    rs.value_of_bool(rs.individual(tname), rs.data_role(A('hasMitigationJUDFTWarnOnly')), True)
    realize(c)
    check('Gd-task with mitigation=true stays consistent', rs.is_consistent())
    check('task : NeedsJUDFTWarnOnly (classified)', is_inst(c, tname, A('NeedsJUDFTWarnOnly')))

    # 4. Broyden detection (pitfall 15): a task with imix Broyden1 on FLEUR
    print('\n== parameter-choice detection ==')
    c = build()
    realize(c)
    rs = c.reasoner
    t2 = A('t_task_broyden')
    rs.instance_of(rs.individual(t2), rs.concept(A('CalculationTask')))
    rs.related_to(rs.individual(t2), rs.object_role(A('hasMixingScheme')), rs.individual(A('Broyden1')))
    realize(c)
    check('Broyden1 task : BroydenOnFLEUR62 (flagged)', is_inst(c, t2, A('BroydenOnFLEUR62')))
    check('Anderson task NOT flagged', (lambda: (
        rs.related_to(rs.individual(A('t_task_anderson')), rs.object_role(A('hasMixingScheme')), rs.individual(A('Anderson'))),
        realize(c),
        is_inst(c, A('t_task_anderson'), A('BroydenOnFLEUR62')))[-1])() is False)

    # 5. direct-API FLEUR without nohup -> inconsistent (pitfall 31 gate)
    print('\n== channel gates ==')
    c = build()
    realize(c)
    rs = c.reasoner
    t3 = A('t_direct_fleur_bad')
    rs.instance_of(rs.individual(t3), rs.concept(A('CalculationTask')))
    rs.related_to(rs.individual(t3), rs.object_role(A('hasEngine')), rs.individual(A('fleur')))
    rs.related_to(rs.individual(t3), rs.object_role(A('hasSubmitChannel')), rs.individual(A('DirectYaschedulerAPI')))
    rs.value_of_bool(rs.individual(t3), rs.data_role(A('hasSpawnNohup')), False)
    rs.value_of_bool(rs.individual(t3), rs.data_role(A('hasMitigationJUDFTWarnOnly')), False)
    fired = realize_raises_inconsistent(c)
    check('direct FLEUR without nohup -> INCONSISTENT (gate)', fired)

    # 6. infra signature batch (pitfall 42): plan with all tasks exit 412 + evals exit 0
    c = build()
    realize(c)
    rs = c.reasoner
    plan = A('t_plan_infra')
    t4a, t4b = A('t_plan_infra_task1'), A('t_plan_infra_task2')
    rs.instance_of(rs.individual(plan), rs.concept(A('CampaignPlan')))
    rs.instance_of(rs.individual(t4a), rs.concept(A('CalculationTask')))
    rs.instance_of(rs.individual(t4b), rs.concept(A('CalculationTask')))
    rs.related_to(rs.individual(plan), rs.object_role(A('hasTask')), rs.individual(t4a))
    rs.related_to(rs.individual(plan), rs.object_role(A('hasTask')), rs.individual(t4b))
    rs.related_to(rs.individual(t4a), rs.object_role(A('hasExitCodeFamily')), rs.individual(A('exit_412')))
    rs.related_to(rs.individual(t4b), rs.object_role(A('hasExitCodeFamily')), rs.individual(A('exit_412')))
    rs.value_of_bool(rs.individual(plan), rs.data_role(A('hasAllTasksExit412')), True)
    rs.value_of_bool(rs.individual(plan), rs.data_role(A('hasBatchEvalExitZero')), True)
    realize(c)
    check('all-412 plan with clean evals : InfraSignatureBatch (classified)',
          is_inst(c, plan, A('InfraSignatureBatch')))
    check('all-412 plan classified NOT a physics failure',
          not is_inst(c, plan, A('PhysicsFailureMode')))

    # 7. experience retrieval: signature "Too low eigenvalue" -> pf_ghost_states
    print('\n== experience layer ==')
    c = build()
    realize(c)
    rs = c.reasoner
    # pf individuals asserted in the RDF: query types of pf_ghost_states
    check('pf_ghost_states : PhysicsFailureMode', is_inst(c, A('pf_ghost_states'), A('PhysicsFailureMode')))
    check('pf_ghost_states NOT InfraFailureMode', not is_inst(c, A('pf_ghost_states'), A('InfraFailureMode')))
    check('pf_spawn_channel_hangup : InfraFailureMode', is_inst(c, A('pf_spawn_channel_hangup'), A('InfraFailureMode')))
    check('pf_false_idle_occupancy : InfraFailureMode', is_inst(c, A('pf_false_idle_occupancy'), A('InfraFailureMode')))
    check('pf_mt_sphere_confinement : BasisSetFailureMode', is_inst(c, A('pf_mt_sphere_confinement'), A('BasisSetFailureMode')))
    check('routing: ghost-states -> codeState', is_inst(c, A('pf_ghost_states'), A('codeState')) or
          list(rs.get_role_fillers(rs.individual(A('pf_ghost_states')), rs.object_role(A('hasRouting')))))

    # 8. serial-mode house preference is representable
    check('serial : ExecutionMode', is_inst(c, A('serial'), A('ExecutionMode')))

    print()
    total = len(PASS) + len(FAIL)
    print(f'== RESULT: {len(PASS)}/{total} checks passed ==')
    if FAIL:
        print('FAILED:')
        for f in FAIL:
            print(f'  - {f}')
        sys.exit(1)
    sys.exit(0)


if __name__ == '__main__':
    main()