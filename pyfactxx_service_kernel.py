"""Kernel wrapper for the aiida-reharness ontology service.

Owns the pyfactxx reasoner instance, the assertion helpers, gate checking
and the experience-layer signature matching. Imported by service.py; can also
be used directly (Kernel(...).diagnose(...)).
"""
import json
import os
import re
import xml.etree.ElementTree as ET

ARH = 'https://mpds.io/ontology#'
BASE = 'http://www.semanticweb.org/ivan/ontologies/2024/0/ontomat#'
RDFNS = 'http://www.w3.org/1999/02/22-rdf-syntax-ns#'

# Mitigation-required (gate) classes and the task booleans each REQUIRES true.
# Derived from aiida_reharness.rdf (gen_aiida_reharness.py equiv_intersection
# calls with gates=[...]); keep in sync when the generator changes.
GATE_CLASSES = {
    'NeedsJUDFTWarnOnly': ['hasMitigationJUDFTWarnOnly'],
    'NeedsSphereCaps': ['hasMitigationSphereCaps', 'hasPerSystemTemplates'],
    'DirectFLEURSubmit': ['hasSpawnNohup', 'hasMitigationJUDFTWarnOnly'],
}

# Detection classes to report when a plan/task individual classifies into them.
DETECTION_CLASSES = [
    'FElementSystem', 'LargeSphereCationSystem', 'NeedsJUDFTWarnOnly',
    'NeedsSphereCaps', 'DirectFLEURSubmit', 'BroydenOnFLEUR62',
    'Broyden2OnFLEUR62', 'InfraSignatureBatch', 'PRDApprovedPlan',
    'TaskExit412',
]

# Experience individuals (pitfalls) with signature matching.
EXPERIENCE_INDIVIDUALS = [
    'pf_ghost_states', 'pf_mt_sphere_confinement', 'pf_broyden_not_implemented',
    'pf_straight_too_conservative', 'pf_walltime_keyerror', 'pf_truncated_outxml',
    'pf_premature_done', 'pf_spawn_channel_hangup', 'pf_false_idle_occupancy',
    'pf_unit_cell_not_neutral', 'pf_wbecke_neighbor_list', 'pf_xinclude_not_flattened',
    'pf_unverified_method_claim', 'pf_orte_resource_exhaustion', 'pf_stale_waiting_wedge',
]

FAILURE_MODES = ['InfraFailureMode', 'PhysicsFailureMode', 'ConvergenceFailureMode',
                'BasisSetFailureMode', 'InputPrepFailureMode', 'DiagnosticsGap']


# Engine individuals named after yascheduler engine keys (see aiida_reharness.rdf).
# 'FLEUR'/'CRYSTAL'/'Inpgen'/'qwen' are CLASSES; fleur/pcrystal/inpgen/qwen are the
# individuals plans assert via hasEngine.
ENGINE_INDIVIDUALS = {'fleur': 'FLEUR', 'pcrystal': 'CRYSTAL', 'inpgen': 'Inpgen',
                      'qwen': 'LLMEngine'}

# The Mac's self-hosted LLM (LM Studio, OpenAI-compatible) for ontology assistance.
QWEN_ENDPOINT = os.environ.get('QWEN_ENDPOINT', 'http://afghani-578.local:1234/v1')
QWEN_MODEL = os.environ.get('QWEN_MODEL', 'qwen/qwen3.8-27b')


class Kernel:
    def __init__(self, base_onto, ext_onto):
        from pyfactxx import coras
        self._coras = coras.Coras()
        self._coras.load(base_onto, format='xml')
        self._coras.load(ext_onto, format='xml')
        self._coras.parse()
        self._coras.realise()
        self.rs = self._coras.reasoner
        self._ext_path = ext_onto
        self._next_id = 0
        self._exp = self._load_experience()

    # ---------------- assertion helpers ----------------

    def indiv(self, prefix):
        """Fresh named individual IRI (unique within this service process)."""
        self._next_id += 1
        return f'{ARH}{prefix}_{os.getpid()}_{self._next_id}'

    def new_indiv(self, cls, prefix=None):
        name = self.indiv(prefix or cls)
        self.assert_type(name, cls)
        return name

    def assert_type(self, indiv, cls):
        self.rs.instance_of(self.rs.individual(indiv), self.rs.concept(ARH + cls))

    def assert_rel(self, subj, prop, obj):
        self.rs.related_to(self.rs.individual(subj),
                           self.rs.object_role(ARH + prop),
                           self.rs.individual(obj if obj.startswith('http') else ARH + obj))

    def assert_bool(self, indiv, prop, value):
        self.rs.value_of_bool(self.rs.individual(indiv),
                              self.rs.data_role(ARH + prop), bool(value))

    def realize_ok(self):
        """Realize; return False iff the kernel failed loud (inconsistent KB)."""
        try:
            self._coras.realise()
            return True
        except RuntimeError as e:
            if 'Inconsistent KB' in str(e):
                return False
            raise

    def is_instance(self, indiv, cls):
        try:
            return self.rs.is_instance(self.rs.individual(indiv), self.rs.concept(ARH + cls))
        except Exception:
            return False

    # ---------------- gate checking (per task) ----------------

    def gate_requirements(self, task_id):
        """Which gate booleans does this task REQUIRE true (via its
        mitigation-required classes)? Call BEFORE asserting task booleans,
       with a consistent realized KB."""
        required = {}
        for cls, bools in GATE_CLASSES.items():
            if self.is_instance(task_id, cls):
                required[cls] = bools
        return required

    # ---------------- experience layer ----------------

    def _load_experience(self):
        tree = ET.parse(self._ext_path)
        root = tree.getroot()
        exp = {}
        for d in root.iter(f'{{{RDFNS}}}Description'):
            about = d.get(f'{{{RDFNS}}}about') or ''
            name = about.split('#')[-1]
            if not about.startswith(ARH) or name not in EXPERIENCE_INDIVIDUALS:
                continue
            entry = {'signatures': [], 'pitfall': None, 'fix': None,
                     'routing': None, 'evidence': None, 'modes': []}
            for child in d:
                tag = child.tag.split('}')[-1].split('#')[-1]  # strip {ns} and ns#
                text = (child.text or '').strip()
                if tag == 'hasSignature':
                    entry['signatures'].append(text)
                elif tag == 'hasPitfallRef':
                    entry['pitfall'] = text
                elif tag == 'hasFix':
                    entry['fix'] = text
                elif tag == 'hasEvidenceCommand':
                    entry['evidence'] = text
            exp[name] = entry
        for name in exp:
            for mode in FAILURE_MODES:
                if self.is_instance(ARH + name, mode):
                    exp[name]['modes'].append(mode)
            for route in ['codeState', 'agentState', 'approvalState', 'waitState']:
                if self.is_instance(ARH + name, route):
                    exp[name]['routing'] = route
                    break
            if exp[name]['routing'] is None:
                # hasRouting is an object-property ASSERTION (not a type):
                # read the role filler instead. The filler reprs as
                # '<Individual object: ...#codeState>' — keep the local name.
                try:
                    fillers = list(self.rs.get_role_fillers(
                        self.rs.individual(ARH + name),
                        self.rs.object_role(ARH + 'hasRouting')))
                    if fillers:
                        raw = str(fillers[0])
                        m = re.search(r'#([A-Za-z]+)', raw)
                        exp[name]['routing'] = m.group(1) if m else raw
                except Exception:
                    pass
        return exp

    def diagnose(self, text, exit_code=None):
        """Match failure text against experience signatures (regex, re.I)."""
        matches = []
        for name, entry in self._exp.items():
            for sig in entry['signatures']:
                try:
                    if re.search(sig, text, re.I):
                        matches.append({
                            'pitfall': entry['pitfall'],
                            'individual': name,
                            'signature': sig,
                            'modes': entry['modes'],
                            'routing': entry['routing'],
                            'fix': entry['fix'],
                            'evidence': entry['evidence'],
                        })
                        break
                except re.error:
                    continue
        return matches

    # ---------------- qwen assist (Mac LM Studio) ----------------

    def qwen_chat(self, messages, timeout_s=600, max_tokens=4000, temperature=0.2):
        """Minimal OpenAI-compatible chat client (stdlib urllib; zero deps).
        Returns the assistant message text. Raises RuntimeError on HTTP errors.

        qwen-3.8 is a REASONING model: it spends tokens on hidden chain-of-thought
        before the visible answer, so max_tokens must be >= 4000 (empirically
        verified: max_tokens=10 yields finish_reason=length with EMPTY content).
        The FIRST call after LM Studio idle also pays the model load (~60-90s)."""
        import urllib.request
        url = QWEN_ENDPOINT.rstrip('/') + '/chat/completions'
        payload = {'model': QWEN_MODEL, 'messages': messages,
                   'max_tokens': max_tokens, 'temperature': temperature}
        req = urllib.request.Request(
            url, data=json.dumps(payload).encode('utf-8'),
            headers={'Content-Type': 'application/json'}, method='POST')
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            body = json.loads(resp.read().decode('utf-8'))
        try:
            return body['choices'][0]['message']['content']
        except (KeyError, IndexError) as e:
            raise RuntimeError(f'qwen response shape unexpected: {e}: {str(body)[:200]}')

    def qwen_warm(self, timeout_s=300):
        """Ping to force LM Studio to load the model; safe to re-run.
        Returns (ok, detail). NOTE: the reasoning model needs max_tokens
        headroom even for a ping (a tiny budget returns empty content)."""
        try:
            self.qwen_chat([{'role': 'user', 'content': 'Reply with exactly: OK'}],
                           timeout_s=timeout_s, max_tokens=1000)
            return True, 'warm'
        except Exception as e:
            return False, f'{type(e).__name__}: {e}'

    def qwen_endpoint_ok(self, timeout_s=8):
        """Health probe for the Mac's LM Studio server."""
        import urllib.request
        try:
            with urllib.request.urlopen(QWEN_ENDPOINT.rstrip('/') + '/models',
                                        timeout=timeout_s) as resp:
                body = json.loads(resp.read().decode('utf-8'))
            ids = [m.get('id') for m in body.get('data', [])]
            return QWEN_MODEL in ids, ids
        except Exception as e:
            return False, [f'{type(e).__name__}: {e}']

# ---------------- km (Kobayashi-MaRust) taxonomy/certification backend ----------------
# Empirically established (Sep 2026 bring-up):
#   - km classifies the merged TBox: consistent=true, 92 subsumptions, route cb_plain8;
#     45/45 parity with pyfactxx on the sampled named-class window.
#   - km's datatype oracle fires functional-data clashes on RAW assertions
#     (direct_clash probe: consistent=false) but NOT through DataPropertyAssertion
#     + class typing (the documented 'data_abox' open corner) — so PLAN GATES
#     stay on pyfactxx; km is the TBox taxonomy/certification backend.
#   - km mapper limits: no owl:AllDisjointClasses (pairwise disjointWith emitted),
#     no rdfs:subPropertyOf (hasElement carries semantics via range only).

KM_BIN = os.environ.get('KM_BIN', '/home/hermes/work/km')
KM_ROUTE = os.environ.get('KM_ROUTE', 'cb_plain8')
MERGED_TTL = os.environ.get('ARH_MERGED_TTL',
                            os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                         'merged_aiida_reharness.ttl'))


def km_classify(timeout_s=240, route=None):
    """Run `km classify` on the merged ontology; return the parsed JSON dict.

    Empirical route facts (Sep 2026): the AUTO route exceeds its worker time
    limit on the merged graph (the 118-individual base triggers a disjunctive
    profile blow-up); cb_plain8 completes in ~15s. cb_plain8 is the default.
    TTL input — km's RDF/XML and TTL mappers agree on our graph but TTL parse
    is faster. The merged TTL must be regenerated by merge_for_km.py +
    rdflib after ontology changes."""
    import subprocess
    cmd = [KM_BIN, 'classify', '--route', route or KM_ROUTE, MERGED_TTL]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s)
    out = (r.stdout + r.stderr).strip()
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        raise RuntimeError(f'km classify failed (exit {r.returncode}): {out[:300]}')


def km_taxonomy_report():
    """Taxonomy + consistency verdict from the Lean-certified engine."""
    res = km_classify()
    A = ARH
    arh = [(s.split('#')[-1], o.split('#')[-1]) for s, o in res.get('subsumptions', [])
           if s.startswith(A) and o.startswith(A)]
    return {
        'backend': 'km (Kobayashi-MaRust v1.4.3, Lean-certified)',
        'consistent': res.get('consistent'),
        'total_subsumptions': len(res.get('subsumptions', [])),
        'arh_subsumptions': len(arh),
        'unsatisfiable': [u.split('#')[-1] if '#' in u else u
                          for u in res.get('unsatisfiable', [])],
        'subsumption_sample': sorted(arh)[:40],
    }

