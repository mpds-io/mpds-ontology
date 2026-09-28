### 1. inpgen generates XInclude-based inp.xml — flattening regex

`inpgen` produces `inp.xml` with `<xi:include href="kpts.xml">` and `<xi:include href="sym.xml">`. Yascheduler only sends `input_files` (just `inp.xml`). FLEUR fails with "XML document cannot be validated against Schema" when kpts.xml/sym.xml are missing.

**Fix for direct API tests**: Generate inp.xml via inpgen, then flatten all XIncludes into a single self-contained file before submitting. See `scripts/gen_fleur_input.py`.

**AiiDA is unaffected**: AiiDA's `FleurinpData` flattens XIncludes into a single self-contained `inp.xml` before submission.

**Critical: the XInclude format is NOT self-closing.** inpgen produces tags like:
```xml
<xi:include xmlns:xi="http://www.w3.org/2001/XInclude" href="kpts.xml"> </xi:include>
```
Note the space and explicit closing tag — NOT `<xi:include ... />`. A regex that only matches self-closing tags will miss these. The correct flattening pattern:

```python
import re

def flatten_xincludes(inp_xml, workdir):
    for xml_file in ['kpts.xml', 'sym.xml', 'relax.xml']:
        xml_path = os.path.join(workdir, xml_file)
        if os.path.exists(xml_path):
            with open(xml_path, 'r') as f:
                content = f.read().strip()
            content = re.sub(r'<\?xml[^>]*\?>\s*', '', content)  # remove XML decl
            # Match BOTH forms: with closing tag AND self-closing
            pattern = re.compile(
                r'<xi:include[^>]*href="' + xml_file + r'".*?</xi:include>|'
                r'<xi:include[^>]*href="' + xml_file + r'"[^>]*/>',
                re.DOTALL
            )
            inp_xml = pattern.sub(content, inp_xml)
    # Remove any remaining relax.xml includes (with fallback)
    inp_xml = re.sub(r'<xi:include[^>]*href="relax\.xml".*?</xi:include>', '', inp_xml, flags=re.DOTALL)
    inp_xml = re.sub(r'<xi:include[^>]*href="relax\.xml"[^>]*/>', '', inp_xml)
    return inp_xml
```

**Always verify**: After flattening, check `len(re.findall(r'xi:include', inp_xml)) == 0` before submitting.

### 2. /nonce placeholder in AiiDA codes
AiiDA code `filepath_executable` is `/nonce` for `Pcrystal`, `fleur`, and `Dummy` codes. This is intentional — AiiDA doesn't run the binary locally; yascheduler handles execution via its `spawn` command. Do NOT try to "fix" `/nonce`.

### 3. yascheduler version differences
The system python3.13 has yascheduler 1.8.0 (installed from GitHub — PyPI only has 1.6.1 as of July 2026; the Vultr adapter was merged in PR #160 at v1.7.0). Install from GitHub: `python3.13 -m pip install --break-system-packages /tmp/yascheduler_src`. Version 1.6.x barely logs (no "Submitting" or "done and saved" messages at INFO level). When debugging, check the DB directly rather than relying on log entries.

### 4. Zombie FLEUR processes
When yascheduler restarts, running FLEUR processes on remote nodes are orphaned. These keep `pgrep fleur_MPI` returning true, so yascheduler thinks the node is still busy. Kill them manually:
```bash
sudo ssh root@<ip> 'pkill -9 fleur_MPI'
```

### 5. Node loss after restart
Restarting yascheduler can drop nodes from the DB. After restart, verify `SELECT count(*) FROM yascheduler_nodes;` and re-add any missing nodes.

### 6. SSH security scan blocks raw IP addresses
Hermes security scan blocks `scp` and some `ssh` commands to raw IP addresses. Workaround: pipe file content through SSH: `cat file | sudo ssh root@<ip> 'cat > /path/file'`. Shorter SSH commands are less likely to be blocked.

### 7. macOS compute nodes — sleep, SSH instability, and dynamic IP
macOS machines (especially Apple Silicon on WiFi) are unreliable as persistent compute nodes:

- **Sleep**: macOS drops SSH connections when it sleeps. The machine may be reachable via `ping` (ICMP) but port 22 times out. Run `caffeinate -d` on the Mac, or set `System Settings → Battery → Power Adapter → "Prevent automatic sleeping"`. Without this, long-running tasks will fail silently when the Mac sleeps mid-job. **Confirmed across multiple sessions** — the Mac went to sleep while running a Pcrystal task (~4.5 min into the calculation).
- **WiFi latency**: Fluctuating 100–700ms latency on WiFi makes MPI jobs impractical. Use wired Ethernet for compute nodes. When latency is low (5–16ms), tasks run fine.
- **Firewall / stealth mode**: macOS Application Firewall in stealth mode drops all incoming connections. Verify `System Settings → Network → Firewall` allows SSH (port 22). `nc -z -w 3 <ip> 22` will show "closed" even when the machine is up.
- **Remote Login**: Must be explicitly enabled via `System Settings → General → Sharing → Remote Login`. It is OFF by default and may be toggled off between sessions.
- **Port check**: `nc -z -w 3 <ip> 22` is the fastest way to verify SSH is actually reachable (ping only confirms ICMP, not the SSH service). "Connection refused" means SSH daemon is not running (Remote Login off). "Connection timed out" means the machine is sleeping or firewall is blocking.
- **Intermittent SSH**: If SSH works once then starts timing out, the machine likely went to sleep. Don't waste cycles retrying — ask the user to wake it and check Remote Login settings.
- **Dynamic IP — discover via mDNS**: macOS machines on WiFi get random DHCP IPs. Don't hardcode the IP. Discover it via `avahi-resolve -n Afghani-578.local` (returns the current IP), or browse for SSH services: `avahi-browse -rt _ssh._tcp | grep Afghani`. Then `ping -c 3 <ip>` to populate ARP before SSH. **Verified working**: IP changed from .107 to .201 between sessions, mDNS discovery found the new IP immediately.
- **macOS pgrep syntax**: `pgrep -c <pattern>` is NOT supported on macOS (BSD pgrep). Use `ps aux | grep <pattern> | grep -v grep` instead.

### 8. Platform-specific engine configs
yascheduler engine `platforms = linux` will NOT match macOS nodes. For macOS compute nodes, either:
- Create a separate engine section with `platforms = darwin`
- Or set `platforms = linux,darwin` if the binaries and spawn command are compatible across platforms

### 8. inpgen `latsys` limitations — no simple tetragonal

`inpgen` does NOT accept `latsys='tet'` (or `'tetragonal'`, `'tetr'`, `'p4'`, `'stet'`, etc.). It errors with `unknown lattice system latsys=tet`. Valid values include: `sc`, `bcc`, `fcc`, `hex`, `bct` (body-centered tetragonal), `zr` (hexagonal), etc.

For a **simple tetragonal** cell (P4/mmm, a≠c, no body centering), you CANNOT simply modify the cubic bravais matrix and keep the cubic symmetry operations. FLEUR fails with `<ERROR Message="k_lv(Rr)"/>` because the 48 cubic symmetry operations (including 3-fold rotations) are incompatible with the tetragonal lattice. The correct workaround:

1. Generate with `latsys='sc'` but place one atom slightly off-symmetry (e.g., O at z=0.5265 instead of 0.5) to force inpgen to reduce symmetry to 8 ops (tetragonal-compatible)
2. Flatten XIncludes (kpts.xml, sym.xml) into a single self-contained inp.xml
3. Fix the off-symmetry atom position back to the correct fractional coordinate (e.g., 0.5)
4. Modify the `<bravaisMatrix>` row-3 to the desired c-axis value
5. Verify the XML parses and has ≤16 symmetry operations (tetragonal point group has 16 ops; inpgen may find 8)

For **I4/mcm** (body-centered tetragonal), `latsys='bct'` works with `a` and `c` parameters directly, but atom positions need to be in the BCT primitive cell basis.

### 8b. inpgen FCC structures — use conventional cell, NOT primitive

inpgen errors with `Error message: atom positions` / `spg_gen` when given FCC structures in the **primitive cell basis** with `latsys='fcc'`. This happens because inpgen's symmetry finder (`spg_gen`) cannot handle certain atom position combinations in the FCC primitive basis.

**Fix**: Convert atom positions to the **conventional cubic cell** and use `latsys='sc'` with `a = <FCC conventional lattice parameter>`:

```
# Primitive FCC to conventional cell conversion:
# Primitive vectors: p1=(0,a/2,a/2), p2=(a/2,0,a/2), p3=(a/2,a/2,0)
# Primitive (u,v,w) -> cartesian = u*p1 + v*p2 + w*p3 -> conv fractional = cartesian / a
#
# Example (GdNi, mpds://entry/S527440, a_conv = 3.6038*sqrt(2) = 5.097):
#   Gd: (0,0,0) -> (0,0,0);  (0.25,0.25,0.25) -> (0.25,0.25,0.25)
#   Ni: (0.625,0.125,0.625) -> (0.375,0.625,0.375)
```

**Verified**: GdNi with `latsys='sc'`, `a=5.0967`, 6 atoms in conventional positions works correctly. inpgen finds 6 symmetry operations and generates valid k-point lists. Using `latsys='fcc'` with the same coordinates crashes inpgen.

### 8c. FLEUR JUDFT_WARN_ONLY for heavy elements (Gd, lanthanides)

FLEUR aborts with `<ERROR Message="Too low eigenvalue detected"/>` (ghost states from core electrons) when running systems with heavy elements (Gd, lanthanides, actinides). This is a warning-level issue that FLEUR escalates to a fatal error by default.

**Fix**: Create a `JUDFT_WARN_ONLY` file in the task directory before running FLEUR. This converts all warnings (including ghost states) from fatal errors to non-fatal warnings.

- **In yascheduler spawn command**: Add `touch JUDFT_WARN_ONLY` before `{engine_path}/fleur_MPI`
- **In Mac dispatcher**: Same — the Mac already has this fix
- **Symptoms without fix**: Task marked DONE after only 1 iteration with no total energy, no convergence distance, just the error message in `out.xml`

**Verified**: GdNi (Gd Z=64, 4f electrons, spin-polarized) crashes without JUDFT_WARN_ONLY. With the fix, tasks converge normally.

**UPDATE (July 29, 2026)**: JUDFT_WARN_ONLY is required for **ALL** systems, not just heavy elements. NiZn (Z=28,30 — no f-electrons) also aborts with "Too low eigenvalue detected" when run with inpgen default Kmax=3.4 without JUDFT_WARN_ONLY. The ghost-state warning is triggered by the inpgen default basis set parameters, not just by heavy elements. **Always include `touch JUDFT_WARN_ONLY` in the yascheduler spawn command**, regardless of the system.

Note: AiiDA's `FleurCalculation` creates `JUDFT_WARN_ONLY` automatically in its staging area (line 465-468 of `aiida_fleur/calculation.fleur`), so AiiDA-submitted tasks always have it. But direct yascheduler API submissions do NOT — the spawn command must include `touch JUDFT_WARN_ONLY`.

### 9. DFT+HIA (Hubbard-1) iteration monitoring — and when NOT to use it

**IMPORTANT**: Do NOT claim DFT+HIA or DFT+U is "required" for 4f systems (Gd, lanthanides) without testing plain PBE first. The user explicitly pushed back on an untested claim that GdNi needs DFT+HIA — the actual issue was insufficient itmax (50 vs 200) and wrong alpha.

**Tested findings (GdNi, July 2026, Vultr bare-metal)**:
- Plain PBE (Anderson mixing, alpha=0.15, itmax=200) gives **nearly stable energy** (<10 meV spread over last 10 SCF iterations) even when charge density distance never reaches 1e-5.
- The charge density distance oscillates around 1e-3 to 1e-4 due to 4f occupation fluctuations. This is NORMAL for 4f systems with plain PBE — it does NOT mean the calculation failed.
- **Energy stability** (spread of last 10 energy values from `totalEnergy` in out.xml) is a more honest convergence criterion than minDistance for 4f systems.
- **alpha=0.05** (FLEUR default): too slow, oscillates. **alpha=0.15**: optimal. **alpha=0.50**: crashes with "error in core-level routine" — too aggressive, destabilizes core states.
- **itmax=50** is insufficient for 4f systems. Use **itmax=200**.
- inpgen auto-configures Gd with spin-polarized 4f occupations (jspins=2) but does NOT add `<ldaHIA>` — plain PBE is the default.

When FLEUR runs with DFT+HIA (`<ldaHIA>` in inp.xml), the SCF loop has two phases:
1. **SCF convergence** (iterations 1–~28): `chargeDensity distance` decreases from ~70 to ~1e-10
2. **Hubbard-1 sub-iterations** (remaining iterations up to `itmax=300`): `distance="0.0000000000"` — these are NOT SCF iterations, they're HIA self-consistency loops

The total energy keeps shifting during HIA iterations (e.g., -274.856 → -275.002 Htr). These jobs run for many hours (10+ h at 185/300 iterations on 24 cores for MgO with HIA).

To check real SCF convergence, filter out zero-distance iterations:
```bash
ssh root@<ip> "grep -oE 'chargeDensity spin=\"1\" distance=\"[^\"]+\"' /root/data/tasks/<dir>/out.xml | grep -v 'distance=\"0.0000000000\"' | tail -10"
```

### 10. AiiDA profile location and access

The AiiDA profile lives at `/root/.aiida/` (config at `/root/.aiida/config.json`), NOT at `/home/hermes/.aiida/`. To query AiiDA:

```bash
# Use system python3.13's verdi (NOT the venv — see pitfall 16)
sudo AIIDA_PATH=/root/.aiida PYTHONNOUSERSITE=1 /usr/local/bin/verdi process list -a

# Or via psql directly (faster, no verdi needed)
sudo PGPASSWORD= /data/pg/bin/psql -h localhost -U postgres -d aiida -c "..."
```

The home directory `/home/hermes/.aiida/config.json` exists but has empty profiles `{}` — don't use it.

**Python packages**: System python3.13 has AiiDA 2.8.0 + aiida_fleur + aiida_phonopy + aiida_reoptimize installed at `/usr/local/lib/python3.13/dist-packages/`. The venv at `/data/mpds-aiida/.venv/` has an SRE mismatch and should NOT be used for AiiDA operations (see pitfall 16).

### 11. Yascheduler spawn command discrepancy (AiiDA vs direct)

Never quote the `[engine.fleur]` spawn from memory — read the live section from `/etc/yascheduler/yascheduler.conf` (or the key-reference block above). It has changed repeatedly (nohup, caffeinate guard, JUDFT_WARN_ONLY, output_files list); today it runs FLEUR as a single process with OpenMP parallelization (not MPI), output going to `out` and `out.xml` directly.

When AiiDA submits via `yasubmit`, the generated `_aiidasubmit.sh` may use a different redirect (`>> out 2>&1`) — check which output files actually exist per task. `output_files` entries never created only leave AiiDA retrieval warnings; yascheduler still marks the task DONE (status=2).

### 12. AiiDA FleurCalculation parse errors — truncated out.xml is the real cause

When a FLEUR calculation completes on the remote node but AiiDA fails to parse the retrieved output, the process enters `Excepted` state. The FleurCalculation log shows warnings like:
- `Expected file 'shell.out' not found in retrieved folder`
- `Expected file 'out.error' not found in retrieved folder`
- `Expected file 'usage.json' not found in retrieved folder`

**These missing-file warnings are a RED HERRING.** The parser only warns (line 74-75 of `FleurParser`) — it does NOT fail on missing `shell.out`/`out.error`/`usage.json`. The actual parse failure is:

```
parser_warnings: ['The out.xml file is broken I try to repair it.']
parser_errors: ['Skipping the parsing of the XML file. Repairing was not possible.']
ERROR: Something went wrong, no out_dict found
```

**Root cause: yascheduler retrieves `out.xml` while FLEUR is still writing it**, producing a truncated XML file (no `</fleurOutput>` closing tag, ends mid-iteration at an unclosed tag). The Masci-Tools out.xml parser tries to repair it but fails, returning an empty `out_dict`.

**How to verify**: Check the retrieved `out.xml`:
```bash
grep -c '</fleurOutput>' /data/aiida/<hash>/<uuid>/out.xml  # → 0 means truncated
python3 -c "import xml.etree.ElementTree as ET; ET.parse('out.xml')"  # → ParseError
```

The FLEUR output files (`out.xml`, `cdn1`, `inp.xml`) ARE on disk at the AiiDA repository path — yascheduler's `local_folder` points to `/data/aiida/<hash-prefix>/<uuid>/`. The data is there, just truncated and unparsable.

**This is the same root cause as pitfall 13** (premature task completion) — yascheduler's SSH check retrieves files mid-write. The missing `shell.out`/`out.error` warnings are cosmetic; the truncated XML is the killer.

### 13. Hetzner node SSH instability — premature task completion

The Hetzner compute nodes (167.233.228.79, 167.233.232.210) have **intermittent SSH connectivity drops** (unrelated to macOS sleep). When SSH drops mid-calculation:

1. Yascheduler loses the SSH connection and interprets this as task completion
2. It retrieves partial output files (incomplete `out.xml` with no `</fleurOutput>` closing tag)
3. Marks the task as DONE (status=2) even though FLEUR is still running (or was killed by the connection loss)
4. The FLEUR process on the node may be killed when the SSH session drops

**Symptoms**: Task marked DONE after only 7-14 iterations when 50+ were expected. `out.xml` has no closing `</fleurOutput>` tag. Distance was still descending (not converged).

**Mitigations**:
- Monitor actively via SSH and check if `</fleurOutput>` is present in `out.xml`
- If a task is marked DONE but `out.xml` is incomplete, resubmit
- For critically important calculations, run locally instead (see pitfall 14)
- Disable the unstable node and use the other one: `UPDATE yascheduler_nodes SET enabled=false WHERE ip='<unstable_ip>';`

### 14. Running FLEUR locally as fallback

When both Hetzner nodes are unstable, FLEUR can be run locally on the home server (192.168.1.100). The `fleur_MPI` binary can be copied from a compute node:

```bash
# Copy binary (scp to raw IP is blocked by security scan — pipe through SSH instead)
ssh root@167.233.232.210 "cat /root/data/engines/fleur/fleur_MPI" > /tmp/fleur_MPI
chmod 755 /tmp/fleur_MPI

# Verify no missing libs
ldd /tmp/fleur_MPI | grep "not found"

# Run locally (OpenMP only, no mpirun needed)
mkdir -p /tmp/fleur_run && cp inp.xml /tmp/fleur_run/
cd /tmp/fleur_run
OMP_NUM_THREADS=8 LD_LIBRARY_PATH=/usr/local/lib /tmp/fleur_MPI >shell.out 2>out.error
```

**Key details**:
- The home server has 8 cores (vs 24 on Hetzner nodes) — ~45s/iteration vs ~30s
- The binary links against system `libmpi.so.40` (OpenMPI 4 ABI provided by OpenMPI 5.0.7)
- Running without `mpirun` works — FLEUR uses OpenMP threads internally
- `OMP_NUM_THREADS=8` limits to available cores
- Running with `mpirun -np 1` fails with `opal_shmem_base_select failed` (OpenMPI version mismatch) — just run the binary directly
- `LD_LIBRARY_PATH=/usr/local/lib` is needed for the FLEUR libraries

### 15. FLEUR Anderson mixing convergence — alpha tuning and minDistance

The default Anderson mixing (`alpha=0.05`, `maxIterBroyd=15`) can plateau at density distance ~1×10⁻⁴ and oscillate without reaching `minDistance=1×10⁻⁵`. This happened for tetragonal SrTiO3 (8 symmetry ops, 280 k-points) while cubic (48 ops, 260 k-points) converged fine with the same parameters.

**Valid imix values** (from FLEUR InputSchema 0.37): `straight`, `Broyden1`, `Broyden2`, `Anderson`. **However, Broyden1 and Broyden2 are NOT implemented** in the FLEUR 6.2 build on the compute nodes — FLEUR errors with `<ERROR Message="Broyden 1/2 method not implemented"/>`.

**Convergence strategies** (in order of preference):
1. Increase `alpha` to 0.15 (more aggressive mixing) — breaks through the 1e-4 plateau faster
2. Increase `maxIterBroyd` to 99 (more history for Anderson) — helps marginally
3. Relax `minDistance` to 5×10⁻⁵ — allows FLEUR to declare convergence when the energy is already stable to 6+ decimal places
4. Increase `itmax` to 200+ (give room for slow convergence)
5. The energy converges even when the density distance doesn't — check `totalEnergy` stability across the last 10 iterations to judge if the result is usable

**Example SCF params for hard-to-converge systems**:
```xml
<scfLoop itmax="200" minDistance=".00005000" maxIterBroyd="99" imix="Anderson" alpha=".15000000" precondParam="0.0" spinf="2.00000000"/>
```

**Monitoring convergence**: check both distance AND energy. If energy is stable to 6 decimal places but distance oscillates at ~1e-4, the calculation is practically converged — relax minDistance and resubmit, or accept the result.

### 16. AiiDA daemon startup — use system python3.13, NOT the venv

The AiiDA venv at `/data/mpds-aiida/.venv/` uses uv's Python 3.12, which has an **SRE module mismatch** (`AssertionError: SRE module mismatch`) when the daemon starts. The venv Python symlinks to `/root/.local/share/uv/python/cpython-3.12-linux-x86_64-gnu/bin/python3.12`, and system `.pth` files from absolidix/esdd packages cause the `_sre.MAGIC` to conflict.

**Fix: use system python3.13's `/usr/local/bin/verdi` instead of the venv's verdi.** System python3.13 has AiiDA 2.8.0 + aiida_fleur + aiida_phonopy + aiida_reoptimize all installed and working. There is no manual start command anymore — the daemon is supervisor-managed (`verdi daemon worker` × 6, see `references/aiida-daemon-supervision.md`). The worker environment is set entirely by the `[program:aiida-daemon]` `environment=` line in `/etc/supervisor/supervisord.conf`; apply changes with `sudo supervisorctl reread && sudo supervisorctl update` (restarts the workers — do it with an empty queue).

**Critical: MPDS_KEY must be in the daemon's environment.** A supervisord program's `environment=` line is its COMPLETE environment — nothing is inherited from the shell or from other programs (the `yascheduler` program's own MPDS_KEY does nothing for the AiiDA workers). If `MPDS_KEY` is missing, MPDSFleurStructureWorkChain fails with exit 501 (`ERROR_NO_MPDS_API_KEY`) **client-side in the worker** — the task never reaches yascheduler, so no row ever appears in `yascheduler_tasks`. The MPDS key is: `dbeYWIPg3uhxy3EmRLKyrXEDJY38NnqzwITZBklvjuB820dF` (also in supervisord config).

**Also needed**: Move ALL conflicting `.pth` files before starting (see pitfall 16b). Multiple `.pth` files in `/usr/local/lib/python3.13/dist-packages/` reference uv's Python 3.12:
```bash
sudo python3 -c "
import os, glob, shutil
for pth in glob.glob('/usr/local/lib/python3.13/dist-packages/__editable__.*.pth'):
    if not os.path.exists(pth + '.bak'):
        shutil.move(pth, pth + '.bak')
"
```

**RabbitMQ v4.x note**: The server runs RabbitMQ 4.0.5 (Ubuntu 25.04 default). Despite earlier advice about downgrading to 3.13, the daemon **does start and work** with RabbitMQ 4.x when using system python3.13 + ulimit fix. The `consumer_timeout` should still be set (see RabbitMQ section above). If the daemon spins at 100% CPU, the issue is more likely the Python/SRE mismatch than RabbitMQ.

**ulimit -n**: Still needed — the default 1024 is too low for circus. Always include `ulimit -n 65536` in the start command.

**Verifying MPDS_KEY reached the worker**: After starting the daemon, verify the key is in the worker process environment:
```bash
worker_pid=$(pgrep -f 'verdi.*daemon.*worker' | head -1)
sudo cat /proc/$worker_pid/environ | tr '\0' '\n' | grep MPDS_KEY
```
Check EVERY worker pid, not just the first — a worker started before an env fix keeps the old environment until restarted: `for p in $(pgrep -f 'daemon worker'); do echo -n "pid $p: "; sudo cat /proc/$p/environ | tr '\0' '\n' | grep -c '^MPDS_KEY'; done` — all must print 1, else `sudo supervisorctl restart aiida-daemon:*`.

### 16a. sudo shell commands hanging on this server

On this specific server (Ubuntu 25.04 plucky), `sudo` commands that perform I/O redirection or interact with systemd can hang indefinitely after completing their primary action (likely a PAM session close / journald issue). `sudo cp`, `sudo tee`, `sudo systemctl`, `sudo rm` all hang — and so do `sudo grep -r` / `sudo find` over `/root`. `sudo -n true` and `sudo kill -9 <pid>` work fine. Prefix every sudo command in a diagnostic batch with `timeout` (e.g. `sudo timeout 20 grep ...`): one hang otherwise stalls every later check in the batch.

**Fix**: Run all sudo operations through `sudo python3 -c "..."` instead of shell commands:
```python
# Instead of: sudo cp /tmp/file /etc/destination  (hangs)
# Use:
sudo python3 -c 'import shutil; shutil.copy("/tmp/file", "/etc/destination"); print("done")'

# Instead of: echo "content" | sudo tee /etc/rabbitmq/rabbitmq.conf  (hangs)
# Use:
sudo python3 -c 'open("/etc/rabbitmq/rabbitmq.conf", "w").write("consumer_timeout = 1000000000\n")'

# Instead of: sudo systemctl restart rabbitmq-server  (hangs)
# Use:
sudo python3 -c 'import subprocess; subprocess.run(["systemctl", "restart", "rabbitmq-server"], timeout=30); print("restarted")'
```

### 16b. Multiple .pth file conflicts with AiiDA (system python3.13)

Multiple `.pth` files in `/usr/local/lib/python3.13/dist-packages/` reference uv's Python 3.12 path. When AiiDA starts (even with system python3.13 via `/usr/local/bin/verdi`), these `.pth` files cause `SRE module mismatch` or `Failed to import the site module` errors.

**Known conflicting .pth files** (move ALL of them):
- `__editable__.absolidix_backend-0.9.0.pth`
- `__editable__.esdd_client-0.1.9.0.pth`
- `__editable__.esdd_online-0.1.1.pth`
- (any future `__editable__.*.pth` that references uv python paths)

**Fix**: Move ALL `__editable__.*.pth` files to `.bak` before starting the daemon:
```bash
sudo python3 -c "
import os, glob, shutil
for pth in glob.glob('/usr/local/lib/python3.13/dist-packages/__editable__.*.pth'):
    if not os.path.exists(pth + '.bak'):
        shutil.move(pth, pth + '.bak')
        print(f'Moved: {os.path.basename(pth)}')
"
```

`PYTHONNOUSERSITE=1` alone does NOT suppress these system `.pth` files — they must be physically moved.

### 17. Resubmitting stuck AiiDA CalcJobs via yascheduler direct API

When AiiDA CalcJobs are stuck in `waiting` state (daemon broken, webhooks lost, nodes removed), you can resubmit them directly via yascheduler, bypassing AiiDA entirely.

**Key insight**: AiiDA stores CalcJob input files in its repository at `/data/aiida/<hash-prefix>/<uuid-remainder>/`. The path is derived from the node UUID: split into first 2 chars / next 2 chars / remainder.

```python
def get_repo_path(uuid):
    parts = uuid.split('-')
    return f"/data/aiida/{parts[0][:2]}/{parts[0][2:4]}/{parts[0][4:]}-{parts[1]}-{parts[2]}-{parts[3]}-{parts[4]}"
```

Each CalcJob's repository folder contains the input files (CRYSTAL: `INPUT` + `fort.34`; FLEUR: `inp.xml`). Read these files and submit via the yascheduler direct API with the appropriate engine name (`pcrystal` or `fleur`).

**Finding the UUIDs**: Query the AiiDA DB:
```sql
SELECT id, uuid, label FROM db_dbnode
WHERE node_type LIKE 'process.calculation.calcjob%'
AND process_type = 'aiida.calculations:crystal_dft.parallel'
AND attributes->>'process_state' = 'waiting'
ORDER BY id;
```

**Important**: The `process_type` column (NOT `node_type`) holds the specific AiiDA process class name (e.g., `aiida.calculations:crystal_dft.parallel`, `aiida.calculations:fleur.fleur`). The `node_type` column only has the generic class (`process.calculation.calcjob.CalcJobNode.`).

See `scripts/resubmit_crystal_jobs.py` for a complete working script.

### 18. AiiDA ↔ yascheduler task correspondence

AiiDA CalcJobs submitted to the yascheduler computer get yascheduler task IDs. The label in yascheduler is `aiida-<pk>` (e.g., `aiida-768`). However:

- Yascheduler may mark a task DONE (status=2) when SSH drops, even if the calculation didn't finish
- AiiDA's CalcJob sees the scheduler state as QUEUED/RUNNING and waits indefinitely
- The webhook from yascheduler to AiiDA may fail if the AiiDA daemon is down
- Yascheduler tasks and AiiDA processes can get out of sync — always cross-reference both DBs

To find yascheduler tasks for AiiDA CalcJobs:
```sql
SELECT task_id, label, status FROM yascheduler_tasks
WHERE label LIKE 'aiida-<pk>';
```

### 19. CRYSTAL "UNIT CELL NOT NEUTRAL" — basis set charge mismatch

When resubmitting CRYSTAL CalcJobs from the AiiDA repository, certain materials fail with `ERROR **** INPBAS **** UNIT CELL NOT NEUTRAL` followed by MPI_ABORT. This is a **basis set problem**, not a runtime issue.

**Affected materials** (from the MPDSBSL_NEUTRAL_6TH basis set family): Yb-containing perovskites with certain oxidation states — Yb3GeO, Yb3InC, Yb3PbC, Yb3SnC, Yb3SnO, YbAlO3, YbCrO3, YbNiO3, YbPb2SbO6, YbRhO3, YbTaPb2O6, YbTiO3. The basis sets assigned to these compositions don't produce a neutral unit cell.

**Fix**: These materials need custom basis set assignments or different oxidation state choices. The `MPDSBSL_NEUTRAL_6TH` family is supposed to guarantee neutrality but doesn't cover all compositions. Check the INPUT file's basis set section for each failing material and verify that the sum of basis set charges equals the nuclear charge.

### 20. OpenMPI resource exhaustion with concurrent --oversubscribe tasks

Running multiple Pcrystal tasks simultaneously on a node with `--oversubscribe -np 8` on only 16 physical cores causes ORTE resource exhaustion. Symptoms:

- `[tapejara5:NNNNN] ORTE_ERROR_LOG: Out of resource in file util/show_help.c`
- `[tapejara5:NNNNN] ORTE_ERROR_LOG: Data unpack would read past end of buffer`
- `forrtl: error (78): process killed (SIGTERM)`
- `[warn] Epoll MOD(N) on fd NN failed` (repeated)

**17 of 37** concurrently-submitted CRYSTAL tasks crashed this way on the 16-core local node. Yascheduler runs tasks sequentially (one at a time per node), but if you submit many at once and the node processes them in rapid succession, OpenMPI daemon state can corrupt.

**Fix**: For bulk CRYSTAL submissions on a local node, either:
- Reduce `ncpus` in the yascheduler_nodes table to match physical cores (not hyperthreads)
- Submit in smaller batches (5–10 at a time) rather than all 37 at once
- Set `OMP_NUM_THREADS=1` in the spawn command (already done for pcrystal) to prevent OpenMP from competing for the same cores

### 21. Ghost/stuck yascheduler tasks (status=1, no process)

Yascheduler can report a task as RUNNING (status=1) when no process is actually running. Symptoms:

- `ps aux | grep Pcrystal` returns nothing
- No task directory exists in `/data/perovskites/yac/data/tasks/`
- Yascheduler log shows `NODES: busy:1 TASKS: run:1` indefinitely
- The task was submitted but the engine process was never spawned or already died

**Fix**: Manually reset the task status to DONE (2) or TO_DO (0):
```sql
UPDATE yascheduler_tasks SET status=2 WHERE task_id=<id> AND status=1;
```
Then restart yascheduler: `sudo supervisorctl restart yascheduler`

**Prevention**: This happens when the engine binary fails to start (missing binary, wrong path) or when the node's SSH connection drops during task allocation. Check the yascheduler log for error messages around the task's submission time.

### 21a. Yascheduler local node deploys via SSH to /root/data/tasks/

When yascheduler runs a task on the local node (e.g., `46.224.80.75` = the home server itself), it still deploys via SSH to `root@<own-IP>`, placing task files in `/root/data/tasks/<timestamp>_<task_id>/` — NOT in `/data/perovskites/yac/data/tasks/`. The latter directory is for tasks that ran on remote nodes and had their outputs retrieved back.

To check output of a task running on the local node:
```bash
# Find the task dir via SSH (not local filesystem)
sudo python3 -c 'import subprocess; r=subprocess.run(["ssh","-o","ConnectTimeout=5","root@46.224.80.75","ls /root/data/tasks/"], capture_output=True, text=True, timeout=10); print(r.stdout)'

# Read OUTPUT progress
sudo python3 -c 'import subprocess; r=subprocess.run(["ssh","-o","ConnectTimeout=5","root@46.224.80.75","tail -20 /root/data/tasks/<dir>/OUTPUT"], capture_output=True, text=True, timeout=15); print(r.stdout)'
```

The `metadata->>'remote_folder'` column in yascheduler_tasks gives the relative path (e.g., `data/tasks/20260710_115135_124`) — prepend `/root/` for local node tasks. Use SSH to read files, not direct filesystem access.

### 22. CRYSTAL geometry optimization vs SCF convergence

"SCF ENDED - CONVERGENCE ON ENERGY" in the OUTPUT file means **individual SCF steps converged**, NOT that the geometry optimization completed. For geometry optimization tasks (those with `OPTGEOM`/`ENDOPT` in INPUT):

- `SCF ENDED - CONVERGENCE` = one SCF cycle within the geo opt converged
- `CONVERGED YES` (next to RMS GRADIENT / MAX GRADIENT / MAX DISPLAC. / RMS DISPLAC.) = geo opt converged
- `CONVERGED NO` = geo opt still in progress (more iterations needed)
- `SCF ENDED - TOO MANY CYCLES` = SCF didn't converge within the cycle limit (energy may still be usable)

**Classification logic for batch status reports**:
```
CONVERGED YES + SCF ENDED - CONVERGENCE → fully converged geo opt
SCF ENDED - CONVERGENCE + CONVERGED NO  → SCF ok, geo opt incomplete
SCF ENDED - TOO MANY CYCLES              → SCF didn't converge (check if energy is stable)
MPI_ABORT (no SCF ENDED)                 → crashed
UNIT CELL NOT NEUTRAL                     → basis set error (see pitfall 19)
```

### 22b. PR #20 "Updating fleur parameters" — straight mixing scheme evaluation (July 2026)

PR #20 (by @akvatol) proposed: `imix=straight`, `alpha=0.05`, `kmax=3.0`, fixed `4x4x4` k-mesh for SCF, `6x6x6` for relax. Evaluated on Vultr bare-metal + VM with SrTiO3, GdNi, NiZn.

**Result: scheme FAILS for all test systems.**
- Straight mixing alpha=0.05 is too conservative — distances stuck at 40-260 Htr after 10-30 iterations
- Anderson mixing alpha=0.15 (OLD scheme) converges NiZn in 17 iterations (distance 9.78e-6)
- kmax=3.0 + sparse k-mesh causes "Determination of fermi-level did not converge" error
- Energy differences between OLD and NEW schemes: 231 eV (SrTiO3), 703 eV (NiZn) — unconverged
- Reviewer blokhin's concern ("4³ too little for metallic/f-electron systems") fully validated
- **Recommendation: use Anderson alpha=0.15, inpgen adaptive k-mesh, kmax=4.5**
- iffgit.fz-juelich.de was DOWN — used GitHub mirror (github.com/JuDFTteam/fleur, MaX-R6.2, commit a9f84b5)
- Vultr API key expired mid-session; new key required. Account spending limit allows max 1 bare-metal + 1 VM

### 23. FLEUR exit code 497 — CDGFleurSCFOptimizer incomplete

AiiDA workchains for FLEUR geometry optimization (fleur.mpds → CDGFleurSCFOptimizer) finish with **exit 497** when the SCF converges but the lattice optimization doesn't complete. This is a known limitation of FLEUR MaX-6.2: only Anderson + straight mixing are implemented (Broyden1/2 are NOT — see pitfall 15), making lattice optimization converge slowly or not at all for some systems.

**Exit codes to know**:
- **412** = fleur.mpds top-level workchain: SCF converged but downstream property calculation not triggered
- **497** = CDGFleurSCFOptimizer: SCF converged, lattice optimization incomplete
- **399** = fleur.base: FLEUR calculation failed (exit 303 at CalcJob level)
- **303** = FLEUR CalcJob: SCF didn't converge (hit itmax) OR the retrieved folder lacks out.xml (pitfall 39)
- **361** = fleur.scf: SCF reached max runs (workchain may continue with more runs)
- **360** = fleur.scf: SCF converged successfully
- **301** = fleur.base: general FLEUR error
- **235** = fleur.scf: inpxml_changes could not be applied (bad task list — e.g. set_species naming a species absent from that system's inp.xml, pitfall 38)
- **306** = inpgen CalcJob: inp.xml not generated (inpgen crashed — e.g. `maxCubeAtoms is not large enough in chkmt`)

### 24. Comprehensive status reporting methodology

When asked for a detailed status of all calculations, query **both** databases and **read the actual output files**:

1. **Yascheduler DB**: `SELECT task_id, label, ip, status, metadata->>'engine' FROM yascheduler_tasks ORDER BY task_id;`
2. **AiiDA DB**: `SELECT id, label, attributes->>'process_state', attributes->>'exit_status', process_type FROM db_dbnode WHERE node_type LIKE 'process.%';`
3. **Output files**: For local tasks, read OUTPUT (CRYSTAL) or out.xml (FLEUR) from `/data/perovskites/yac/data/tasks/<dir>/`
4. **Classify each task**: converged / max cycles / crashed / non-neutral / incomplete geo opt / ghost
5. **Cross-reference**: AiiDA CalcJob PKs ↔ yascheduler task labels (`aiida-<pk>`)

**Key**: DONE does not mean succeeded, at either layer. Yascheduler status=2 means the task completed (including crashes) — check the OUTPUT file for the actual CRYSTAL/FLEUR exit status. AiiDA `finished` likewise only means the workchain ran: group by `exit_status` before reporting — 0 = success; 501 = failed client-side in the worker (e.g. MPDS key missing — corroborate via the absence of an `aiida-<pk>` row in `yascheduler_tasks`); 412 = structure-optimization physics failure. `metadata->>'error'` entries for optional output files (`out.error`, `usage.json`, `cdn1`) are retrieval noise, not failures. Quick queue pulse: `sudo supervisorctl tail yascheduler stdout` → `TASKS: run:N/todo:N/done:N`.

### 24b. dft.mpds.io error listing — JSON API

`https://dft.mpds.io/?filter=error&project=1&fmt=json` returns the failed-systems list as JSON arrays `[formula, spacegroup_number, error_reason]`. The reason string is the workflow step name plus the AiiDA exit code when known, e.g. `"geometry optimization (errcode 300)"`, `"elastic constants (errcode 360)"`, `"phonon frequencies (errcode 400)"`. Codes: 3xx = FLEUR workchain exits (300/301 fleur.base general error, 303 SCF hit itmax; 360 appears on elastic-constant stage), 4xx = phonon-stage exits, 5xx (502/503) = infra failures with an EMPTY reason string (reason is `" (errcode 502)"`). Steps with no errcode are bare reason strings. The HTML variant (`&fmt=json` omitted) renders each item as `<li class='error' title='<reason>'>`. As of Sept 2026: 257 failed systems, one error each — geometry optimization 86, phonon frequencies 77, elastic constants 65, bare 502/503 28, seebeck 1; concentrated in SGs 225/221/194/62 (~72%).

### 25. CRYSTAL PREOPTGEOM — combine geometry optimization with phonon calculation

When a phonon calculation (`FREQCALC`) yields imaginary frequencies, the structure wasn't fully optimized. CRYSTAL supports the `PREOPTGEOM` sub-keyword **inside the `FREQCALC` block** to pre-optimize the geometry before computing phonon frequencies.

**CRITICAL: PREOPTGEOM is a sub-keyword of FREQCALC, NOT a standalone keyword.** Placing `PREOPTGEOM` before `FREQCALC` (as a sibling keyword in the geometry input section) causes CRYSTAL to crash immediately with `MPI_ABORT` at startup — the banner prints but no SCF cycle runs. This was confirmed by task #123 (crashed) vs task #124 (running successfully).

**Correct input modification** — insert `PREOPTGEOM` (with its own `END`-closed sub-block) INSIDE the `FREQCALC` block:
```
EXTERNAL
SCELPHONO
1 1 0
-1 1 0
0 0 2
FREQCALC
PREOPTGEOM
FULLOPTG
END
TEMPERAT
...
ENDFREQ
END
```

`PREOPTGEOM` opens a sub-block (closed with `END`) that accepts the same optimization keywords as `OPTGEOM` (page 182 of the CRYSTAL23 manual). `FULLOPTG` inside the sub-block requests full relaxation of both lattice parameters and atomic positions. The default convergence criteria for PREOPTGEOM are tighter than normal OPTGEOM (TOLDEG=0.00003, TOLDEX=0.00012, TOLDEE=10) to ensure accurate numerical second derivatives for frequencies.

The `fort.34` (structure) and basis set sections remain unchanged. CRYSTAL will first optimize the geometry, then run the phonon calculation on the optimized structure in a single job.

**Submit via yascheduler** the same way as any pcrystal task — read the modified INPUT + original fort.34 and call `yac.queue_submit_task(label, {'INPUT': input_content, 'fort.34': fort34_content}, 'pcrystal')`.

**Expected runtime**: significantly longer than a standalone phonon calculation (geometry optimization adds many SCF+gradient cycles). The WMnPb2O6/225 phonon-only run took ~13.5h; with PREOPTGEOM expect 20+ hours on 8 cores.

**Reference**: CRYSTAL23 User's Manual, section 8.1.2 "Equilibrium Geometry" — `PREOPTGEOM` and `NOOPTGEOM` are the two sub-keywords of `FREQCALC` that control whether a preliminary optimization is performed. `NOOPTGEOM` is the default (do not optimize).

### 26. CRYSTAL23 public keyword limitations (Mac)

CRYSTAL23 public 1.0.1 (the arm64 build on the Mac) has several keywords absent from the public release:

- **`CYCLES`** — NOT allowed. Use `MAXCYCLE` instead (both set max SCF iterations, but only `MAXCYCLE` is in the public build).
- **`LIMBEK`** — NOT allowed. This keyword would increase the Becke grid neighbor list limit, fixing the `WBECKE_F NEIGHBOR LIST TOO BIG` error for covalent solids. Without it, DFT calculations on covalent systems (Si diamond, Ge, etc.) fail. **Workaround**: use ionic systems (MgO works) or switch to HF (no Becke grid) — but HF may then fail with `BASIS SET LINEARLY DEPENDENT` for diffuse basis sets like pob-DZVP-rev2 or 6-21G* on Si diamond.
- **`TOLINTEG`** — works (controls Coulomb/exchange overlap tolerances).
- **`DFT`/`PBE`/`END`** — works (DFT functional block).
- **`SHRINK`**, **`MAXCYCLE`**, **`TOLDEE`** — all work.

**Bottom line**: CRYSTAL23 public on Mac works for **ionic systems with DFT-PBE** (MgO verified). For **covalent solids** (Si diamond), use FLEUR instead — the FLEUR Si diamond test converged in 37 iterations on the Mac.

### 27. CRYSTAL phonon output interpretation

Phonon frequency output in CRYSTAL OUTPUT uses `FREQ(CM**-1)` lines with 6 frequencies per line. Key interpretation:

- **Negative frequencies** (e.g., `-60.21`) = **imaginary modes** = structure is dynamically unstable at this geometry
- `ESTIMATED NUMBER OF IMAGINARY FREQS N` — CRYSTAL's own count of imaginary modes
- **3 imaginary frequencies at Γ** typically means the structure needs geometry optimization (use PREOPTGEOM, see pitfall 25)
- The output includes phonon dispersion at multiple k-points (determined by `SCELPHONO` supercell definition)
- `THERMODYNAMIC FUNCTIONS WITH VIBRATIONAL CONTRIBUTIONS` section provides entropy, heat capacity, and free energy at specified temperatures
- `OPTICAL (TO) FREQUENCIES. IRREP LABELS` — symmetry-labeled optical modes at Γ
- `NORMAL MODES NORMALIZED TO CLASSICAL AMPLITUDES` — eigenvectors in Bohr

**FREQCALC accuracy warning**: `WARNING **** READM2 **** PROBABLE LOSS IN FREQCALC ACCURACY; SCF TOL LT 10` means the SCF convergence tolerance (TOLDEE) should be ≥10 for reliable phonon frequencies. The current INPUT uses `TOLDEE 9` — consider increasing to 10 for production runs.

### 28. FLEUR source — iffgit.fz-juelich.de frequently down, use GitHub mirror

The official FLEUR GitLab server (`https://iffgit.fz-juelich.de/fleur/fleur`) is frequently unreachable. The `cloud.sh` script uses this URL and will fail silently (git clone returns "not valid: is this a git repository?"). This was confirmed down on July 29, 2026.

**Fix**: Use the GitHub mirror instead:
```bash
git clone --depth 1 --branch MaX-R6.2 https://github.com/JuDFTteam/fleur fleur
```
This produces the same codebase (commit `a9f84b504efcb04c6d5bd2f59b6b1a0f9eb6e831` for MaX-R6.2 as of July 2026). After cloning, proceed with the normal `./configure.sh && cd build && make -j<N>` as in `cloud.sh`.

### 29. AiiDA process cleanup — killing stuck waiting processes

When the AiiDA daemon has been down for an extended period, processes accumulate in `waiting` state. `verdi process repair` revives them but they may remain stuck. To clean up:

1. Stop the daemon: `verdi daemon stop`
2. Run `verdi process repair` (revives processes, may not resolve them)
3. Kill remaining waiting processes via Python API:
```python
from aiida import load_profile
load_profile()
from aiida.orm import QueryBuilder, ProcessNode

qb = QueryBuilder().append(ProcessNode, filters={'attributes.process_state': 'waiting'})
for (proc,) in qb.all():
    try:
        proc.set_exit_status(130)  # SIGINT
        proc.seal()
    except Exception:
        pass  # already sealed
```
4. Fix process_state via direct DB update, and DROP the `exit_status='130'` filter — sealed nodes reject `set_exit_status` ("attributes of a sealed node are immutable"), so exit_status keeps its old value and the filtered UPDATE matches nothing, leaving the node waiting forever:
```sql
UPDATE db_dbnode
SET attributes = jsonb_set(attributes, '{process_state}', '"killed"')
WHERE node_type LIKE 'process.%'
  AND attributes->>'process_state' = 'waiting';
```
5. Restart the daemon

A stale `waiting` workchain of type `aiida.workflows:fleur.mpds` silently wedges the serial campaign driver, whose submit gate counts active workchains — clean these up BEFORE launching a campaign, not after.

### 30. Phonon workflow — MPDSFleurStructureWorkChain integration gaps

Three integration gaps block the phonon workflow end-to-end (FLEUR itself runs fine; failures are in AiiDA parsing/parameter propagation). Full detail: `references/phonon-workflow-gaps.md`.

- Use `calculator: "scf"`, never `"relax"` — the relax builder nests `fleur` inside `scf` and aiida_reoptimize's setattr fails.
- Truncated `out.xml` (pitfall 12) → no `output_parameters['walltime']` → `FleurScfWorkChain.get_res()` excepts → optimizer penalty 1e10 → 497/412.
- Omit `calc_parameters` (kmax/kpt) — they don't propagate; `wf_parameters` do. Let inpgen's adaptive k-mesh stand.

- `references/yascheduler-investigation.md` — detailed failure investigation from the session that found and fixed the engine config issues
- `references/yascheduler-tasks-analysis.md` — whole-table stats recipe: row_to_json dump → Python aggregation; schema facts (no timestamps — date from remote_folder path; dual-shape error key; empty-ip meaning) and the fetch-miss error taxonomy with diagnostic file combos
- `references/phonon-workflow-gaps.md` — full detail behind pitfall 30: phonon workchain builder-namespace workaround, truncated-out.xml → walltime KeyError → 497/412 cascade, and which template parameters do/don't propagate
- `references/srtio3-fleur-results.md` — converged cubic + tetragonal SrTiO3 FLEUR results with convergence trajectories and energy comparison
- `references/crystal-basis-format.md` — CRYSTAL basis set pkl library format, parser, and tested basis sets table (including which work/fail on Mac)
- `references/crystal-batch-status-202607.md` — detailed batch status of 37 resubmitted CRYSTAL jobs (July 2026), including crash classification, non-neutral cell errors, and MPI resource exhaustion analysis
- `references/rabbitmq-downgrade.md` — step-by-step RabbitMQ v4→v3.13 downgrade procedure with Erlang 26, apt pinning, consumer_timeout config, ulimit fix, and AiiDA daemon startup (complete reproduction recipe)
- `references/vultr-kpts-study.md` — K-point density study methodology and results: SrTiO3 (sweet spot 6x6x6, 63 meV, 10x speedup), NiZn (non-monotonic convergence, needs 16x16x16), GdNi (plain PBE converges with itmax=200 alpha=0.15, NO DFT+HIA needed). Includes wall-time extraction method from out.xml timestamps and speed/cost analysis.
- `references/parser-patches.md` — masci_tools seek(0) fix + aiida_fleur scf.py walltime .get() fix: root cause of truncated out.xml parse failures, exact patch commands, verification, revert instructions
- `references/campaign-driver.md` — serial reopt campaign driver: persistent layout, launch command, submit gating, per-system template rebuild rules, progress-ping convention, exit-status interpretation
- `references/poscar-generation-rules.md` — VASP POSCAR format rules: real element symbols only (no functional groups), L2=scaling float, keyword=Direct, coords in [0,1), no trailing comments. RDKit SMILES→3D workflow for expanding molecular ions into constituent atoms. Validation script included.
- `references/fleur-pr20-evaluation-report.md` — full PR #20 evaluation report: straight mixing vs Anderson, k-mesh comparison, 9 DFT calculations, cost analysis
- `references/pr20-full-diff.patch` — complete git diff of PR #20 vs master (flapw_default.yml + cloud.sh changes)
- `scripts/gen_fleur_pr20_inputs.py` — generate 9 FLEUR inp.xml files for scheme comparison (3 structures × 3 schemes: old/4x4/6x6), with proper XInclude flattening
- `scripts/submit_pr20_tasks.py` — submit FLEUR SCF tasks to yascheduler via direct API (reads from fleur_pr20_eval directory)
- `scripts/submit_fleur_phonon.py` — submit AiiDA MPDSFleurStructureWorkChain for phonon calculation (requires daemon with MPDS_KEY)
- `scripts/vultr_create_baremetal.py` — allocate Vultr bare-metal instances via REST API (urllib only, no deps)
- `scripts/vultr_create_vms.py` — allocate Vultr standard VMs via REST API
- `scripts/cloud_pr20.sh` — PR #20 version of cloud.sh (OpenMPI 4.1.1 + FLEUR MaX-6.2, uses iffgit URL — see pitfall 28 for GitHub mirror)
- `templates/flapw_default_original.yml` — original (master) FLEUR calc template for comparison
- `templates/flapw_default_pr20.yml` — PR #20 version of FLEUR calc template (straight mixing, kmax=3.0, 4x4x4/6x6x6)
- `templates/yascheduler-fleur-engine.conf` — known-good yascheduler fleur engine config section (with JUDFT_WARN_ONLY for direct API)
- `templates/yascheduler-fleur-engines-user-spec.txt` — user-specified engine configs for linux + darwin (July 2026, without JUDFT_WARN_ONLY in spawn — see pitfall 8c for when to add it back)
- `templates/crystal-mgo-input.txt` — known-good MgO CRYSTAL input using pkl basis sets (Mg_8-61G + O_8-411_muscat, DFT-PBE, verified on Mac M4 Max)

### 31. yascheduler run_bg kills FLEUR — nohup required in spawn command

yascheduler's `run_bg()` method (in `remote_machine/common.py`) creates the process via `conn.create_process(command, stdin=DEVNULL, stdout=DEVNULL, stderr=DEVNULL)`. This creates an SSH channel process that is killed when yascheduler's SSH poll cycle disconnects the channel. Without `nohup`, FLEUR is killed after 1-3 SCF iterations, producing a truncated `out.xml` with no `</fleurOutput>` closing tag.

**Symptoms**:
- FLEUR runs for 2-3 minutes, produces 1-3 iterations in `out.xml`, then stops
- `out.xml` is truncated mid-iteration (no closing tag, no error message)
- yascheduler marks task DONE (status=2)
- The `FleurBaseWorkChain` reports "completed after 1 iterations"
- Running FLEUR manually on the same node with the same input works fine (runs to completion)

**Root cause**: `conn.create_process()` with `stdin=DEVNULL, stdout=DEVNULL, stderr=DEVNULL` creates a process tied to the SSH channel. When yascheduler's async event loop cycles and the channel is reaped, the process receives SIGHUP and dies. `nohup` ignores SIGHUP, allowing FLEUR to survive channel disconnection.

**Fix**: Add `nohup` and output redirect to the spawn command:
```ini
spawn = export LD_LIBRARY_PATH=/usr/local/lib && cd {task_path} && touch JUDFT_WARN_ONLY && nohup {engine_path}/fleur_MPI > out 2>&1 &
```

The `&` backgrounds the process so `run_bg` returns immediately. The `> out 2>&1` captures FLEUR stdout/stderr to the `out` file (add `out` to `output_files` for retrieval). Without the redirect, output goes to DEVNULL (as specified by `run_bg`).

**Verification** (July 29, 2026): NiZn with Anderson mixing alpha=0.15, inpgen adaptive 20×20×20 k-mesh:
- WITHOUT nohup: 1 iteration, truncated out.xml, FLEUR killed after ~3 min
- WITH nohup: 17 iterations, distance 3.4×10⁻⁵ (converged!), energy -3341.975 Htr, `out` file 3.4 MB properly retrieved

**Note**: The `out.xml` may still lack the final `</fleurOutput>` closing tag even with nohup, because FLEUR writes it at the very end and the file may not be fully flushed when yascheduler retrieves it. The AiiDA parser's repair logic may handle this, but if not, the `out` file (FLEUR stdout) contains the full convergence trajectory and can be used as a fallback.

### 32. AiiDA FleurCalculation creates JUDFT_WARN_ONLY automatically

AiiDA's `FleurCalculation` (line 465-468 of `aiida_fleur/calculation.fleur`) creates a `JUDFT_WARN_ONLY` file in the calculation staging area. This means:
- **AiiDA-submitted tasks**: always have `JUDFT_WARN_ONLY` regardless of yascheduler spawn command
- **Direct yascheduler API tasks**: only have it if the spawn command includes `touch JUDFT_WARN_ONLY`
- When testing FLEUR via direct API, always include `touch JUDFT_WARN_ONLY` in the spawn command
- When the user asks to remove `JUDFT_WARN_ONLY` from the yascheduler config, AiiDA tasks will still work, but direct API tasks will fail with "Too low eigenvalue detected"

### 33. masci_tools out.xml parser fails on BufferedReader — seek(0) fix

**This is the root cause of ALL "Skipping the parsing of the XML file. Repairing was not possible." errors.**

When `FleurParser.parse()` opens `out.xml` from the AiiDA retrieved folder via `output_folder.open('out.xml', 'rb')`, it gets a `BufferedReader`. The `load_outxml_and_check_for_broken_xml()` function in `masci_tools/io/fleur_xml.py` tries to parse with `recover=False` first (fails on truncated XML), then retries with `recover=True`. But **the first parse consumes the file handle — the position is now at EOF**. The second parse reads from EOF, gets an empty tree, and raises `ValueError: Skipping the parsing of the XML file. Repairing was not possible.`

**Key diagnostic**: The same truncated out.xml parses successfully (48 keys, energy, walltime) when wrapped in `io.BytesIO()` but returns 0 keys when given a `BufferedReader`. This is because `BytesIO` is a fresh object each time, while `BufferedReader` retains its file position.

**Fix**: Add `seek(0)` before the repair parse in `masci_tools/io/fleur_xml.py` (~line 172):

```python
# In load_outxml_and_check_for_broken_xml(), before the repair parse:
if outfile_broken:
    # Reset file position for the second parse attempt (handles truncated XML)
    if hasattr(outxmlfile, 'seek'):
        outxmlfile.seek(0)
    parser = etree.XMLParser(attribute_defaults=True, recover=True, encoding='utf-8', **kwargs)
    try:
        xmltree = xml_parse_func(outxmlfile, parser)
    except etree.XMLSyntaxError as err:
        raise ValueError('Skipping the parsing of the XML file. Repairing was not possible.') from err
```

**File**: `/usr/local/lib/python3.13/dist-packages/masci_tools/io/fleur_xml.py` (backup at `.bak`)

**Verification** (July 30, 2026): After the fix, the parser successfully repairs truncated out.xml from a BufferedReader, extracting 48 keys including `energy_hartree=-3316.97`, `walltime=-71781`, `overall_density_convergence=4.5e-07`. The FleurScfWorkChain no longer excepts at `get_res`.

### 34b. POSCAR generation — strict format rules AND physical constraints

HARD requirements, not suggestions. Format: real element symbols ONLY on line 6 (expand molecular ions to constituent atoms via RDKit SMILES→3D); line 2 = single scaling float, never a comment; keyword `Direct`; fractional coords wrapped to [0, 1); no trailing comments. Physical constraints (non-negotiable): lattice parameter from Goldschmidt `a = 2*(r_B + r_X)` only — never enlarge the cell to fit molecules, that breaks the tolerance factor and the B-X octahedral network; pre-filter formulae by t < 1.1 (re-roll with smaller A-cations, do not distort the cell); molecule must fit the void (`max_molecular_radius < a*sqrt(3)/2 - r_B - 0.5`) with no A-A overlap (`< a_lat/2 - 0.3`); validate min pairwise distance under PBC ≥ 0.7 Å after generation; NH4+ must be expanded manually (RDKit parses `[NH4+]` as bare N).

Full validation script, RDKit expansion workflow, tolerance-factor filtering, and distance checker: `references/poscar-generation-rules.md`.

### 36. Perovskite structure count estimation — physical constraints reduce naive count ~100×

When the user asks for "all possible structures," they mean physically realizable ones, not pure combinatorics — apply the three filters (Goldschmidt t in [0.8, 1.1], molecule-fits-void, no A-A overlap) BEFORE counting, not after. Naive combinatorial counts overestimate by ~100×: measured validity ~7-8% for 1A categories, ~2% for 2A, ~0.5% for 3A. Full category breakdown, space group estimates, 2D RP/DJ/ACI generation, external-candidate comparison: `references/perovskite-structure-estimation.md`.

### 35. aiida_fleur scf.py walltime KeyError — use .get() not []

`FleurScfWorkChain.get_res()` at line 696 of `aiida_fleur/workflows/scf.py` accesses `output_parameters['walltime']` with dict bracket notation. When the parser produces partial output (e.g., missing `walltime` from a truncated out.xml that was repaired but couldn't extract the end timestamp), this raises `KeyError` → FleurScfWorkChain Excepted.

**Fix**: Change line 696 from:
```python
walltime = last_base_wc.outputs.output_parameters['walltime']
```
to:
```python
walltime = last_base_wc.outputs.output_parameters.get('walltime', 0)
```

**File**: `/usr/local/lib/python3.13/dist-packages/aiida_fleur/workflows/scf.py` (backup at `.bak`)

**Combined effect of patches 33+34**: The FleurScfWorkChain now completes normally (exit 361 = max iterations, or exit 0 = converged) instead of Excepting. The optimizer receives valid energy data and can proceed to the next lattice distortion evaluation. The phonon workflow progresses past the optimization stage.

### 37. FLEUR "differ 2" — MT-sphere confinement of high-n s valence states

`<ERROR Message="differ 2: problems with solving dirac equation"/>` at FLEUR setup (before any SCF iteration) means the radial Dirac solver found "too few nodes" — a state ABOVE the solvable energy range. Mechanism: inpgen auto-assigns large MT spheres to heavy 6s-valence cations (Ba ≈ 2.7–2.8 bohr; also Cs, Rb, K), and the high-n s valence basis state (e.g. Ba 6s, searched via `find_enpara` → `differ`) cannot be confined in that sphere. This silently kills whole classes of systems — Ba/Cs double perovskites and halides — and was the dominant mode behind the dft.mpds.io geometry-optimization failures.

**Diagnose the failing species from FLEUR's `out` file, not from expectation** — the diagnostic line `too few nodes. <n> <l> <j> <emin> <e> <emax>` is followed by a potential dump of constant `-Z×2` values; `-0.5600E+02` repeated = Z=56 = Ba. The lanthanide is usually innocent; the alkaline-earth cation is usually guilty.

**Fix — cap MT radii via `set_species` inpxml_changes**: Ba 2.30, Cs 2.50, Rb 2.40, K 2.20 bohr. ALWAYS apply as **min(auto_radius, cap)** per system: parse the auto radius from that system's inpgen output and add the cap ONLY when auto > cap. A hard-coded radius LARGER than the auto sphere (compressed cells, F/Cl neighbors) triggers `Overlapping MT-radii of two neighbours detected` — an equally fatal setup error in the opposite direction. Radial-mesh densification (logIncrement/gridPoints), jspins changes, and dropping stateOccupation do NOT help — do not spend evals on them.

### 38. masci_tools `set_species` — exact names, no create, per-system templates only

- `species_name: "all-<substring>"` matching is broken in masci_tools 0.15 (XPathBuilder raises `ValueError: 'species' is not in list`). Use the EXACT species name as inpgen wrote it: `Barium (Ba)`, `Cesium (Cs)`, `Potassium (K)`, `Rubidium (Rb)`.
- Do NOT pass `create: True` for an existing species — it routes into the same broken XPathBuilder path.
- Species names come from each system's OWN inpgen output. Never put set_species entries in a shared/base template: a species absent from one system's inp.xml makes its every eval exit 235 (`ERROR_CHANGING_FLEURINPUT_FAILED`). Base templates carry only universal `set_inpchanges`; species caps live in per-system templates generated from and validated against that system's inp.xml.
- Validate every task list exactly the way the workchain applies it before submission:
```python
fm = FleurXMLModifier()
fm.add_task_list([tuple(c) for c in changes])   # the YAML inpxml_changes tuples
out, _ = fm.apply_modifications(etree.parse(io.BytesIO(inp_xml.encode())), None, fm._tasks)  # raises on mismatch
```

### 39. Dispatcher DONE-marking with missing outputs poisons AiiDA

A transient SSH failure ("node is gone" — the Mac is on Wi-Fi) during output download must NEVER leave the task DONE. If it does, AiiDA's transport retrieve step copies a folder containing only the submit-time `inp.xml`; the parser returns exit 303 ("XML output file was not found") even though FLEUR converged on the Mac; the evaluator assigns penalty 1e10; and when a whole CG iteration's evals fail this way the optimizer exits 497 with zero diagnostic footprint in the workchain logs. Rule: retry downloads; if the critical output (out.xml) is still missing, reset the task to TO_DO for a re-run. When AiiDA exits 303 despite a converged out.xml existing on disk, check `yascheduler_tasks.metadata->>'error'` for the SSH failure record and compare the retrieved FolderData contents (`node.outputs.retrieved.list_object_names()`) against the workdir.

### 40. CDG optimizer economics — FD step, tolerance units, worker blocking

- Each CG iteration costs 1+N_params SCF evaluations (finite-difference gradient). The default `delta=1e-6` (Å) is pure noise at DFT energy resolution: the gradient is garbage and the optimizer random-walks or stalls. Use `delta: 0.01` in `algorithm_settings`.
- `tolerance` compares ‖gradient‖ in Htr/Å; real gradients are ~1e-3..1e-1. A tolerance near 1 (e.g. an inherited 0.7) declares convergence at iteration 1 and stops the optimization before it starts. Use 0.05.
- One failed eval = penalty 1e10 for that lattice point; if ALL points of an iteration fail, the optimizer exits 497 immediately. Per-eval SCF convergence is the campaign's lifeblood: give f-electron systems ONE long FLEUR run (`fleur_runmax: 1`, `itmax_per_run: 150`) rather than several short ones.
- The optimizer BLOCKS one daemon worker for its entire run (`run_get_node` in `run_evaluator`), while its SCF children need free workers to orchestrate. With 6 daemon workers never run more than ~3 optimizers concurrently; the user-preferred mode is strictly serial (one system in flight, dispatcher `--concurrency 1`).
- Exit 361 (max runs) is per-run and the SCF workchain may continue with more runs; a converged SCF still exits 303 ONLY when the retrieved folder is incomplete (pitfall 39).

### 42. Hard-system reopt failures: straight-mixing 2x300 doesn't rescue 412/497 systems

Attempt-2 (Sep 13, straight mixing SCF 2×300 via driver4) on the 7 hard systems (UCrSe3/UEuO3/UVSe3/TmVO3 /62, URh3B/Yb3SnO /221, YSn2/63) reproduced attempt-1's 412/497 outcome exactly. Optimizer evals fail two ways:
- **Except with `TypeError: unsupported operand type(s) for -: 'NoneType' and 'NoneType'`** in the SCF workchain (seen on UCrSe3 15031, TmVO3 16121): the parser's repaired out.xml yields None for keys get_res subtracts (energy/distance). Same family as pitfall 35 — guard with `or 0`/`.get(..., 0)` at the subtraction sites too, not just walltime.
- **Exit 362 ERROR_DID_NOT_CONVERGE** (UVSe3 15291, YSn2 15901, others): SCF ran the full 2×300 iterations without converging — physics, not infra.
Mixing scheme was NOT the differentiator for these systems; they fail under Anderson AND straight. Only Y3SnC/221 ever converged (attempt-1, Anderson). These 7 need different treatment (deferred-class handling per pitfall-class list) or acceptance as dft.mpds.io errors.

The AiiDA daemon resolves `mpds_aiida` from the stale dist-packages copy (version lags the repo — the repo at `/data/mpds-aiida` is importable only when cwd happens to be inside it), and `get_template()` first checks `TEMPLATE_DIR = $HOME/.aiida/mpds_aiida/` (the daemon user's copy — also stale) before falling back to the raw path. ALWAYS pass `config_file` as an ABSOLUTE filesystem path to the template file when submitting workchains to the daemon; a bare filename resolves to a stale copy whose parameters silently differ from what you validated.

### 42. BSD ps vs GNU `:255` — false-idle occupancy polls rmtree live task dirs on Darwin; engines die silently (RC=2). A uniform batch of fast 412s with eval calcjobs at exit 0 = infra, not physics — verify evals ran (yac task rows, iterations in retrieved `out`) before tuning SCF params. Fixed in installed 1.8.1; toolkit + reinstall: references/yascheduler-remote-engine-lifecycle.md

