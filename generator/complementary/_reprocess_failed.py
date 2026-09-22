"""Reprocessa os estados CAR que falharam (bug do round/NA e geometria mista),
um por vez em subprocessos isolados (memória liberada entre estados). Log UTF-8 limpo."""
import subprocess, sys, os, time
sys.stdout.reconfigure(encoding="utf-8")

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(BASE, "..", ".."))
LOG = os.path.join(ROOT, "data", "car_reprocess.log")
PY = os.path.join(BASE, ".venv", "Scripts", "python.exe")
UFS = ["TO", "MT", "MA", "PA", "GO", "PR", "RS", "MG"]  # ascendente por tamanho; MG por último
env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")


def log(m):
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(m + "\n")
    print(m, flush=True)


log(f"=== REPROCESS INICIO {time.strftime('%Y-%m-%d %H:%M:%S')} : {UFS} ===")
for uf in UFS:
    log(f"--- {uf} inicio {time.strftime('%H:%M:%S')} ---")
    t0 = time.time()
    p = subprocess.run(
        [PY, "-u", os.path.join("process", "process_car.py"), "--uf", uf, "--force"],
        cwd=BASE, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    dt = int(time.time() - t0)
    out = (p.stdout or "").strip()
    err = (p.stderr or "").strip()
    if p.returncode == 0:
        last = out.splitlines()[-1] if out else "(sem stdout)"
        log(f"[OK] {uf} ({dt}s): {last}")
    else:
        log(f"[ERRO] {uf} rc={p.returncode} ({dt}s)")
        if err:
            log("STDERR(tail):\n" + "\n".join(err.splitlines()[-18:]))
    log(f"--- {uf} fim {time.strftime('%H:%M:%S')} ---")
log(f"=== REPROCESS FIM {time.strftime('%Y-%m-%d %H:%M:%S')} ===")
