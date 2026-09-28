#!/usr/bin/env python3
"""
aiida-reharness runtime service: pyfactxx-backed campaign-plan validation +
failure diagnosis, driven from reharness FSM code leaves over a JSON-per-line
stdin/stdout protocol (one request per line, one response per line).

Protocol (JSON per line):
  {"op": "ping"}
  {"op": "validate_plan", "plan": {
       "booleans": {"prdApproved": true, ...},
       "systems": [{"elements": ["Gd", "Ni"]}],
       "tasks": [{"engine": "FLEUR", "channel": "DirectYaschedulerAPI",
                  "mixing": "Anderson", "system": 0,
                  "booleans": {"hasSpawnNohup": true, ...}}]}}
  {"op": "diagnose", "text": "<failure text>", "exit_code": 412}
  {"op": "quit"}

Gate semantics (closed-world, fail-loud):
  1. The caller must assert prdApproved explicitly (missing = error).
  2. Task structure (engine/channel/mixing/system-links) is asserted first;
     one realization classifies each task into its mitigation-REQUIRED classes.
  3. Each required boolean must be present AND true; a false/missing required
     boolean is reported by name (precise gate attribution) and the plan is
     rejected. This is a deterministic pre-check; the kernel consistency gate
     remains the backstop: after all booleans are asserted, the KB must stay
     consistent (any residual inconsistency = rejection).
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ONT_DIR = HERE
BASE_ONTO = os.path.join(ONT_DIR, 'mpds_ontology.rdf')
EXT_ONTO = os.path.join(ONT_DIR, 'aiida_reharness.rdf')

ARH = 'https://mpds.io/ontology#'
BASE = 'http://www.semanticweb.org/ivan/ontologies/2024/0/ontomat#'

sys.path.insert(0, HERE)
from pyfactxx_service_kernel import (  # noqa: E402
    Kernel, GATE_CLASSES, DETECTION_CLASSES, FAILURE_MODES, QWEN_ENDPOINT,
    ENGINE_INDIVIDUALS,
)


def fail(msg):
    return {'ok': False, 'error': msg}


def handle_ping(k, req):
    return {'ok': True, 'service': 'aiida-reharness-ontology', 'version': 1}


def handle_validate_plan(k, req):
    plan = req.get('plan')
    if not isinstance(plan, dict):
        return fail('plan must be an object')

    booleans = plan.get('booleans', {})
    if 'prdApproved' not in booleans:
        return fail('closed-world violation: plan.booleans.prdApproved missing '
                    '(assert every gate boolean explicitly)')
    if booleans['prdApproved'] is not True:
        return {'ok': True, 'runnable': False,
                'reason': 'PRD not approved: the human approves the intent, never the '
                          'graph. Approve the PRD before running.',
                'violations': [], 'classes': []}

    systems = plan.get('systems', [])
    tasks = plan.get('tasks', [])

    # -- phase 1: assert structure, realize, classify --
    plan_id = k.indiv('plan')
    k.assert_type(plan_id, 'CampaignPlan')
    for name, value in booleans.items():
        k.assert_bool(plan_id, name, value)

    system_ids = []
    for s in systems:
        sys_id = k.new_indiv('DFTSystem')
        system_ids.append(sys_id)
        for el in s.get('elements', []):
            k.assert_rel(sys_id, 'hasElement', BASE + el)

    task_ids = []
    for t in tasks:
        t_id = k.new_indiv('CalculationTask')
        task_ids.append(t_id)
        engine = t.get('engine', 'fleur')
        if engine not in ENGINE_INDIVIDUALS:
            return fail(f'unknown engine: {engine!r} (known: '
                        f'{", ".join(sorted(ENGINE_INDIVIDUALS))})')
        k.assert_rel(t_id, 'hasEngine', engine)
        channel = t.get('channel', 'AiiDAWorkChain')
        if channel not in ('AiiDAWorkChain', 'DirectYaschedulerAPI'):
            return fail(f'unknown channel: {channel!r}')
        k.assert_rel(t_id, 'hasSubmitChannel', channel)
        if 'mixing' in t:
            k.assert_rel(t_id, 'hasMixingScheme', t['mixing'])
        if isinstance(t.get('system'), int) and 0 <= t['system'] < len(system_ids):
            k.assert_rel(t_id, 'hasSystem', system_ids[t['system']])
        k.assert_rel(plan_id, 'hasTask', t_id)

    if not k.realize_ok():
        return {'ok': True, 'runnable': False,
                'reason': 'ONTOLOGY GATE REJECTED the plan: structure alone is '
                          'inconsistent (bad engine/channel/mixing combination).',
                'violations': [{'error': 'structural inconsistency'}], 'classes': []}

    # -- phase 2: gate pre-check with precise attribution --
    violations = []
    for t, t_id in zip(tasks, task_ids):
        required = k.gate_requirements(t_id)
        for cls, bools in required.items():
            for b in bools:
                stated = t.get('booleans', {}).get(b)
                if stated is not True:
                    violations.append({
                        'task': tasks.index(t),
                        'gate_class': cls,
                        'boolean': b,
                        'stated': stated,
                        'problem': 'missing' if stated is None else 'false',
                    })
    if violations:
        return {'ok': True, 'runnable': False,
                'reason': 'ONTOLOGY GATE REJECTED the plan: required mitigation '
                          'booleans missing or false.',
                'violations': violations, 'classes': []}

    # -- phase 3: assert all task booleans; kernel consistency backstop --
    for t, t_id in zip(tasks, task_ids):
        for name, value in t.get('booleans', {}).items():
            k.assert_bool(t_id, name, value)
    if not k.realize_ok():
        return {'ok': True, 'runnable': False,
                'reason': 'ONTOLOGY GATE REJECTED the plan: the KB became inconsistent '
                          'after boolean assertion (contradictory mitigations).',
                'violations': [{'error': 'consistency backstop'}], 'classes': []}

    classes = []
    for c in DETECTION_CLASSES:
        if k.is_instance(plan_id, c):
            classes.append(c)
    sys_classes = {}
    for i, sid in enumerate(system_ids):
        hit = [c for c in DETECTION_CLASSES if k.is_instance(sid, c)]
        if hit:
            sys_classes[systems[i].get('formula', f'system_{i}')] = hit
    task_classes = {}
    for i, t_id in enumerate(task_ids):
        hit = [c for c in DETECTION_CLASSES if k.is_instance(t_id, c)]
        if hit:
            task_classes[f'task_{i}'] = hit

    return {'ok': True, 'runnable': True,
            'reason': 'plan passed all ontology gates',
            'violations': [], 'classes': classes,
            'system_classes': sys_classes, 'task_classes': task_classes}


def handle_diagnose(k, req):
    text = str(req.get('text', ''))
    matches = k.diagnose(text, req.get('exit_code'))
    return {'ok': True, 'matches': matches}


def handle_assist(k, req):
    """qwen (Mac LM Studio, qwen-3.8) assistance with the ontology.

    Modes:
      - {"op": "assist", "mode": "diagnose", "text": "...", "exit_code": 412}:
        first try experience signatures; if NO match, ask qwen to CLASSIFY the
        failure text against the failure-mode taxonomy and PROPOSE a pitfall
        candidate (never a fix on its own authority — it proposes, the human
        / experience layer disposes).
      - {"op": "assist", "mode": "axioms", "question": "..."}: free ontology
        question grounded with the taxonomy summary.
      - {"op": "assist", "mode": "status"}: qwen endpoint health.
    """
    mode = req.get('mode', 'status')
    if mode == 'status':
        ok, ids = k.qwen_endpoint_ok()
        warm_ok, warm_detail = k.qwen_warm()  # load the model if cold (~60-90s)
        return {'ok': True, 'endpoint': QWEN_ENDPOINT,
                'model_ok': ok, 'warm': warm_ok, 'warm_detail': warm_detail,
                'models': ids[:8]}
    if mode == 'axioms':
        question = str(req.get('question', ''))
        if not question.strip():
            return fail('axioms mode requires a question')
        system = ('You are an OWL 2 ontology engineering assistant for the '
                  'aiida-reharness project (extension of the MPDS materials ontology, '
                  'reasoner: FaCT++ via pyfactxx). Answer concisely about classes, '
                  'object/datatype properties, individuals, equivalentClass '
                  'intersection definitions, and hasValue consistency gates on '
                  'functional boolean properties. Give Turtle or RDF/XML fragments '
                  'when proposing axioms. Known failure-mode taxonomy: '
                  + ', '.join(FAILURE_MODES) + '.')
        try:
            answer = k.qwen_chat([{'role': 'system', 'content': system},
                                  {'role': 'user', 'content': question}])
        except Exception as e:
            return fail(f'qwen unavailable: {e}')
        return {'ok': True, 'answer': answer}
    if mode == 'diagnose':
        text = str(req.get('text', ''))
        matches = k.diagnose(text, req.get('exit_code'))
        if matches:
            return {'ok': True, 'source': 'experience', 'matches': matches}
        # No signature matched: qwen fallback — classify + propose, clearly labeled
        system = ('You are a failure-triage assistant for DFT campaign operations '
                  '(FLEUR/CRYSTAL via yascheduler + AiiDA). Classify the failure text '
                  'into exactly one mode from: ' + ', '.join(FAILURE_MODES) + '. '
                  'Then propose the most likely known pitfall family (ghost states '
                  'JUDFT_WARN_ONLY; MT-sphere confinement differ 2; Broyden not '
                  'implemented; truncated out.xml; premature DONE; spawn-channel '
                  'hangup nohup; false-idle occupancy; UNIT CELL NOT NEUTRAL; '
                  'WBECKE neighbor list; XInclude not flattened; ORTE exhaustion; '
                  'stale waiting workchain) and ONE deterministic evidence command '
                  'to confirm it. You PROPOSE only; never assert a fix as final.')
        try:
            answer = k.qwen_chat([{'role': 'system', 'content': system},
                                  {'role': 'user', 'content': text}])
        except Exception as e:
            return {'ok': False, 'source': 'none',
                    'error': f'no experience match and qwen unavailable: {e}'}
        return {'ok': True, 'source': 'qwen', 'matches': [], 'proposal': answer}
    return fail(f'unknown assist mode: {mode}')


def handle_taxonomy(k, req):
    """Lean-certified taxonomy verdict from the km backend (Kobayashi-MaRust).
    Reports consistency + subsumption taxonomy of the merged ontology. The
    plan GATES stay on pyfactxx (km's data-assertion ABox corner is open);
    this op is the TBox certification view."""
    import pyfactxx_service_kernel as K
    return {'ok': True, 'taxonomy': K.km_taxonomy_report()}


def handle_validate_learn_delta(k, req):
    """Validate an axiom DELTA (Turtle text) proposed by the learn agent.

    Both backends must accept:
      1. pyfactxx: base + extension + delta parsed and realized — the KB
         must stay CONSISTENT (fail-loud; gates keep working).
      2. km (Lean-certified): the merged TBox + delta classified —
         consistent AND zero newly-unsatisfiable classes.

    Returns {ok, consistent, backends: {pyfactxx: ..., km: ...}, reason}.
    """
    ttl = str(req.get('ttl', ''))
    if not ttl.strip():
        return fail('empty delta')
    import tempfile, os, subprocess
    import pyfactxx_service_kernel as K

    # --- pyfactxx leg ---
    try:
        import rdflib
        g = rdflib.Graph()
        g.parse(K.MERGED_TTL, format='turtle')
        g.parse(data=ttl, format='turtle')
        merged_tmp = tempfile.NamedTemporaryFile(suffix='.ttl', delete=False)
        g.serialize(merged_tmp.name, format='turtle')
    except Exception as e:
        return {'ok': False, 'consistent': False, 'reason': f'delta does not parse: {e}'}
    py_ok = False
    py_detail = ''
    try:
        from pyfactxx import coras
        c2 = coras.Coras()
        c2.load(merged_tmp.name, format='turtle')
        c2.parse()
        c2.realise()
        py_ok = True
        py_detail = 'consistent'
    except RuntimeError as e:
        py_detail = f'inconsistent: {str(e)[:150]}'
    except Exception as e:
        py_detail = f'{type(e).__name__}: {str(e)[:150]}'
    os.unlink(merged_tmp.name)

    # --- km leg (Lean-certified taxonomy check on the same merged graph) ---
    km_ok = False
    km_detail = ''
    try:
        merged2 = tempfile.NamedTemporaryFile(suffix='.ttl', delete=False)
        g.serialize(merged2.name, format='turtle')
        r = subprocess.run(
            [K.KM_BIN, 'classify', '--route', K.KM_ROUTE, merged2.name],
            capture_output=True, text=True, timeout=240)
        out = (r.stdout + r.stderr).strip()
        os.unlink(merged2.name)
        import json as _json
        j = _json.loads(out)
        km_ok = bool(j.get('consistent')) and not j.get('unsatisfiable')
        km_detail = (f"consistent={j.get('consistent')} "
                     f"unsat={len(j.get('unsatisfiable') or [])} "
                     f"subsumptions={len(j.get('subsumptions') or [])}")
    except Exception as e:
        km_detail = f'{type(e).__name__}: {str(e)[:150]}'

    accepted = py_ok and km_ok
    return {
        'ok': True,
        'consistent': accepted,
        'backends': {'pyfactxx': py_detail, 'km (Lean-certified)': km_detail},
        'reason': ('delta accepted by both backends' if accepted else
                   f'rejected: pyfactxx[{py_detail}] km[{km_detail}]'),
    }


OPS = {
    'ping': handle_ping,
    'validate_plan': handle_validate_plan,
    'diagnose': handle_diagnose,
    'assist': handle_assist,
    'taxonomy': handle_taxonomy,
    'validate_learn_delta': handle_validate_learn_delta,
}


def main():
    k = Kernel(BASE_ONTO, EXT_ONTO)
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError as e:
            resp = fail(f'bad JSON: {e}')
        else:
            op = req.get('op')
            if op == 'quit':
                sys.stdout.write(json.dumps({'ok': True, 'bye': True}) + '\n')
                sys.stdout.flush()
                break
            handler = OPS.get(op)
            if handler is None:
                resp = fail(f'unknown op: {op}')
            else:
                try:
                    resp = handler(k, req)
                except Exception as e:  # fail loud, but keep serving
                    resp = fail(f'{type(e).__name__}: {e}')
        sys.stdout.write(json.dumps(resp) + '\n')
        sys.stdout.flush()


if __name__ == '__main__':
    main()