"""Real headless calculation, network-isolated with bubblewrap where available.
No eval, no simulated calculation. A fresh LO profile is used for every batch.
"""

import os
import shutil
import signal
import subprocess
from pathlib import Path

from openpyxl import load_workbook

from app.core.config import ENGINE_TIMEOUT


class EngineError(RuntimeError):
    pass


class LibreOfficeEngine:
    name = "LibreOffice Calc"

    def __init__(self):
        self.binary = shutil.which("libreoffice") or shutil.which("soffice")
        self.bwrap = shutil.which("bwrap")
        self.isolated = False
        if self.bwrap:
            probe = subprocess.run(
                [
                    self.bwrap,
                    "--unshare-all",
                    "--ro-bind",
                    "/usr",
                    "/usr",
                    "--symlink",
                    "usr/bin",
                    "/bin",
                    "--symlink",
                    "usr/lib",
                    "/lib",
                    "--symlink",
                    "usr/lib64",
                    "/lib64",
                    "/usr/bin/true",
                ],
                capture_output=True,
                timeout=5,
            )
            self.isolated = probe.returncode == 0

    def info(self):
        version = (
            subprocess.run(
                [self.binary, "--version"], capture_output=True, text=True, timeout=10
            ).stdout.strip()
            if self.binary
            else "not installed"
        )
        return {
            "name": self.name,
            "version": version,
            "isolated": self.isolated,
            "trust_mode": "network-disabled bubblewrap; unprivileged; resource limited"
            if self.isolated
            else "trusted generated workbooks only; uploads cannot execute",
        }

    def calculate(self, workdir: Path, filenames: list[str], sheet: str, target: str, trusted=True):
        if not self.binary:
            raise EngineError("LibreOffice is not installed; see docs/troubleshooting.md")
        if not trusted and not self.isolated:
            raise EngineError("Strong isolation unavailable: uploaded workbook execution blocked")
        workdir = workdir.resolve()
        (workdir / "out").mkdir(exist_ok=True)
        if self.isolated:
            command = [
                self.bwrap,
                "--unshare-all",
                "--die-with-parent",
                "--new-session",
                "--cap-drop",
                "ALL",
                "--ro-bind",
                "/usr",
                "/usr",
                "--symlink",
                "usr/bin",
                "/bin",
                "--symlink",
                "usr/lib",
                "/lib",
                "--symlink",
                "usr/lib64",
                "/lib64",
                "--proc",
                "/proc",
                "--dev",
                "/dev",
                "--tmpfs",
                "/tmp",
                "--dir",
                "/etc",
                "--dir",
                "/var",
                "--dir",
                "/var/cache",
                "--bind",
                str(workdir),
                "/work",
                "--chdir",
                "/work",
                "--setenv",
                "HOME",
                "/tmp",
                "--setenv",
                "SAL_USE_VCLPLUGIN",
                "svp",
            ]
            for path in [
                "/etc/fonts",
                "/etc/libreoffice",
                "/etc/ld.so.cache",
                "/etc/passwd",
                "/etc/group",
                "/var/cache/fontconfig",
            ]:
                if Path(path).exists():
                    command += ["--ro-bind", path, path]
            prefix = "/work"
        else:
            command = []
            prefix = str(workdir)
        command += [
            self.binary,
            f"-env:UserInstallation={('file:///work/profile' if self.isolated else (workdir / 'profile').as_uri())}",
            "--headless",
            "--nologo",
            "--nodefault",
            "--nolockcheck",
            "--norestore",
            "--convert-to",
            "xlsx",
            "--outdir",
            f"{prefix}/out",
        ] + [f"{prefix}/{f}" for f in filenames]
        # prlimit applies inherited CPU/address-space/file-size/process limits without
        # thread-unsafe Python preexec_fn. Limit the complete process group by timeout.
        if shutil.which("prlimit"):
            command = [
                "prlimit",
                "--cpu=60",
                "--as=2147483648",
                "--fsize=52428800",
                "--nofile=256",
                "--",
            ] + command
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
            env={
                "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                "LANG": "C.UTF-8",
                "HOME": str(workdir),
            },
        )
        try:
            stdout, stderr = process.communicate(timeout=ENGINE_TIMEOUT)
        except subprocess.TimeoutExpired as exc:
            if os.name == "posix":
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
            process.communicate()
            raise EngineError("Calculation timeout; worker process group terminated") from exc
        values = []
        for filename in filenames:
            output = workdir / "out" / filename
            if process.returncode or not output.exists():
                raise EngineError(
                    f"Calculation failed ({process.returncode}): {stderr.decode(errors='replace')[-1000:]} {stdout.decode(errors='replace')[-500:]}"
                )
            wb = load_workbook(output, data_only=True, read_only=True)
            value = wb[sheet][target].value
            wb.close()
            values.append(value)
        return values
