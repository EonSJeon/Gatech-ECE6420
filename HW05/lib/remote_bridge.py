"""Local notebook -> SSH Spectre worker -> numerical data -> local plotting."""
from dataclasses import dataclass
import json
import os
import re
import shlex
import subprocess
from runtime import ROOT


@dataclass
class RemoteConfig:
    host: str = "gt-ece"
    directory: str = "/nethome/sjeon84/Gatech-ECE6420/HW05"
    python: str = ".venv/bin/python"
    hostname: str = ""

    @classmethod
    def load(cls):
        values = {}
        path = ROOT / ".remote.env"
        if path.exists():
            for line in path.read_text().splitlines():
                fields = shlex.split(line, comments=True)
                if not fields:
                    continue
                if len(fields) != 1 or "=" not in fields[0]:
                    raise ValueError(".remote.env accepts KEY=value lines only")
                key, value = fields[0].split("=", 1)
                values[key] = value
        values.update(os.environ)
        config = cls(values.get("HW05_REMOTE_HOST", cls.host),
                     values.get("HW05_REMOTE_DIR", cls.directory),
                     values.get("HW05_REMOTE_PYTHON", cls.python),
                     values.get("HW05_SSH_HOSTNAME", ""))
        if not re.fullmatch(r"[A-Za-z0-9_.@-]+", config.host):
            raise ValueError("Invalid SSH host")
        if not re.fullmatch(r"/[A-Za-z0-9_./-]+/HW05", config.directory) or ".." in config.directory:
            raise ValueError("Remote directory must be an absolute project path ending in /HW05")
        if not re.fullmatch(r"[A-Za-z0-9_./-]+", config.python):
            raise ValueError("Invalid remote Python path")
        if config.hostname and not re.fullmatch(r"[A-Za-z0-9_.-]+", config.hostname):
            raise ValueError("Invalid SSH hostname")
        return config

    def ssh(self):
        command = ["ssh", "-4", "-o", "LogLevel=ERROR", "-o", "ControlMaster=no", "-o", "ControlPath=none",
                   "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", "-o", "ServerAliveInterval=30"]
        if self.hostname:
            command += ["-o", f"HostName={self.hostname}"]
        return command

    def command(self, script):
        return self.ssh() + [self.host, "bash -c " + shlex.quote(script)]


def run_command(command, payload=None):
    """Stream worker progress into the local notebook and surface SSH/Spectre errors."""
    with subprocess.Popen(command, stdin=subprocess.PIPE if payload is not None else subprocess.DEVNULL,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1) as process:
        if payload is not None:
            process.stdin.write(payload)
            process.stdin.close()
        try:
            for line in process.stdout:
                print(line, end="", flush=True)
            status = process.wait()
        except BaseException:
            process.terminate()
            process.wait()
            raise
    if status:
        raise RuntimeError(f"Remote operation failed (exit {status}). Check VPN / ssh gt-ece and the worker log above.")


def rsync(config, source, destination, *, excludes=(), delete=False, dry_run=False, ignore_existing=False):
    command = ["rsync", "-az", "--itemize-changes", "--exclude=.DS_Store"]
    if delete:
        command.append("--delete")
    if dry_run:
        command.append("--dry-run")
    if ignore_existing:
        command.append("--ignore-existing")
    command += [f"--exclude={pattern}" for pattern in excludes]
    command += ["-e", shlex.join(config.ssh()), str(source), str(destination)]
    run_command(command)


def push_sources(config=None, dry_run=False):
    config = config or RemoteConfig.load()
    if not dry_run:
        run_command(config.command("mkdir -p " + " ".join(shlex.quote(config.directory+suffix) for suffix in ("", "/results", "/simulation", "/netlists/generated"))))
    # Mirror the maintained source. Excluded runtime/data paths are protected.
    rsync(config, str(ROOT) + "/", f"{config.host}:{config.directory}/",
          excludes=(".venv/", ".remote.env", "__pycache__/", ".ipynb_checkpoints/",
                    "/simulation/", "/results/", "/netlists/generated/"),
          delete=True, dry_run=dry_run)
    for name in ("migration_manifest.json", "hw5_meta.json", "hw5_full_terminal.txt"):
        rsync(config, ROOT / "results" / name, f"{config.host}:{config.directory}/results/",
              dry_run=dry_run, ignore_existing=True)


def pull_data(config=None, dry_run=False):
    config = config or RemoteConfig.load()
    for path in ("results", "netlists/generated", "simulation"):
        (ROOT / path).mkdir(parents=True, exist_ok=True)
        excludes = ("figures/", "spectral_review.json") if path == "results" else (
            "local-executed/", "matplotlib/", "ipython/", "executed/")
        rsync(config, f"{config.host}:{config.directory}/{path}/", str(ROOT / path) + "/",
              excludes=excludes, dry_run=dry_run)


def run_remote_parts(parts="bcdefg", parameters=None):
    """Called by a local Run cell. Never fetches plots or notebook outputs."""
    parts = "".join(parts)
    if not parts or any(part not in "bcdefg" for part in parts):
        raise ValueError("Select one or more parts from b,c,d,e,f,g")
    config = RemoteConfig.load()
    print(f"Local notebook -> {config.host}:{config.directory} -> parts {parts}", flush=True)
    push_sources(config)
    script = f"cd {shlex.quote(config.directory)} && {shlex.quote(config.python)} tools/remote_worker.py --parts {parts}"
    try:
        run_command(config.command(script), json.dumps(parameters or {}))
    except BaseException:
        try:
            pull_data(config)
        except Exception as exc:
            print(f"Data fetch after failure: {exc}")
        raise
    pull_data(config)
    print("Numerical data received. The following cells render plots on this local kernel.", flush=True)
