"""Long-lived model processes, one per environment (NeMo, Qwen, Omnilingual, HF, WhisperX, enhance).

Each worker is `venvs/<env>/bin/python workers/<env>_worker.py`. It loads models lazily, keeps the
last one in memory, and answers JSON-line requests on stdin/stdout:
    -> {"id": 1, "model": "egyptalk-rnnt", "paths": [...], "opts": {...}}
    <- {"id": 1, "texts": [...], "seconds": 1.2}      or      {"id": 1, "error": "..."}
"""
import json
import os
import subprocess
import threading
from collections import OrderedDict

from .config import APP_DIR, ENVS_DIR, LOG_DIR, MAX_WORKERS


class WorkerError(RuntimeError):
    pass


def env_python(env: str):
    if os.name == "nt":
        return ENVS_DIR / env / "Scripts" / "python.exe"
    return ENVS_DIR / env / "bin" / "python"


def env_installed(env: str) -> bool:
    return env_python(env).exists()


def _log_tail(path, n=30):
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").replace("\r", "\n").splitlines()
        return "\n".join([l for l in lines if l.strip() and "%|" not in l][-n:])
    except FileNotFoundError:
        return ""


class Worker:
    def __init__(self, env: str):
        py = env_python(env)
        if not py.exists():
            raise WorkerError(f"Environment '{env}' is not installed. Run:  ./setup_envs.sh {env}")
        self.env = env
        self.log_path = LOG_DIR / f"worker_{env}.log"
        self._log = open(self.log_path, "a", encoding="utf-8")
        self._id = 0
        self.proc = subprocess.Popen(
            [str(py), str(APP_DIR / "workers" / f"{env}_worker.py")],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self._log,
            text=True, encoding="utf-8", bufsize=1, cwd=str(APP_DIR), env=os.environ.copy())
        self._read()                       # wait for {"ready": true}

    def _read(self):
        while True:
            line = self.proc.stdout.readline()
            if not line:
                raise WorkerError(f"Worker '{self.env}' stopped (exit code {self.proc.poll()}). "
                                  f"Last log lines ({self.log_path}):\n{_log_tail(self.log_path)}")
            line = line.strip()
            if line.startswith("{"):
                return json.loads(line)

    def alive(self):
        return self.proc.poll() is None

    def call(self, model: str, paths, opts=None):
        self._id += 1
        req = {"id": self._id, "model": model, "paths": [str(p) for p in paths], "opts": opts or {}}
        try:
            self.proc.stdin.write(json.dumps(req, ensure_ascii=False) + "\n")
            self.proc.stdin.flush()
        except BrokenPipeError:
            raise WorkerError(f"Worker '{self.env}' is not running. Log:\n{_log_tail(self.log_path)}")
        resp = self._read()
        if "error" in resp:
            raise WorkerError(f"[{model}] {resp['error']}\n(details in {self.log_path})")
        return resp

    def close(self):
        try:
            self.proc.stdin.close()
            self.proc.terminate()
            self.proc.wait(timeout=20)
        except Exception:
            self.proc.kill()
        self._log.close()


class WorkerPool:
    """Keeps at most MAX_WORKERS environments alive; the least recently used one is stopped first."""

    def __init__(self, max_workers=MAX_WORKERS):
        self.max = max(1, max_workers)
        self.workers = OrderedDict()
        self.lock = threading.Lock()

    def call(self, env, model, paths, opts=None):
        with self.lock:
            w = self.workers.get(env)
            if w is None or not w.alive():
                while len(self.workers) >= self.max:
                    _, old = self.workers.popitem(last=False)
                    old.close()
                w = Worker(env)
                self.workers[env] = w
            self.workers.move_to_end(env)
            try:
                return w.call(model, paths, opts)
            except WorkerError:
                if not w.alive():
                    self.workers.pop(env, None)
                raise

    def close_all(self):
        with self.lock:
            for w in self.workers.values():
                w.close()
            self.workers.clear()


POOL = WorkerPool()
