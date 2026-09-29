"""Locate and run the JDK and Maven.

Lookup order: LTW_JAVA_HOME / JAVA_HOME, then PATH, then a sibling `.tools` folder next to
the repo (where a developer without admin rights can unzip a JDK and Maven). Nothing is
downloaded by this module; it only finds what is already there and says clearly when it
cannot.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LEGACY = ROOT / "legacy"
GENERATED_TESTS = LEGACY / "src" / "test" / "java"
PACKAGE = "org.apache.commons.codec.language"


class ToolchainError(RuntimeError):
    pass


@dataclass(frozen=True)
class Toolchain:
    java_home: Path
    mvn: Path

    @property
    def java(self) -> Path:
        return self.java_home / "bin" / ("java.exe" if os.name == "nt" else "java")

    @property
    def javac(self) -> Path:
        return self.java_home / "bin" / ("javac.exe" if os.name == "nt" else "javac")

    def env(self) -> dict[str, str]:
        env = dict(os.environ)
        env["JAVA_HOME"] = str(self.java_home)
        env["PATH"] = str(self.java_home / "bin") + os.pathsep + env.get("PATH", "")
        env.setdefault("MAVEN_OPTS", "-Djava.awt.headless=true")
        return env

    def run_mvn(
        self, *args: str, cwd: Path = LEGACY, profile: str | None = None, timeout: int = 1800
    ) -> subprocess.CompletedProcess:
        cmd = [str(self.mvn), "-q", "-B", "-ntp"]
        if profile:
            cmd.append(f"-P{profile}")
        cmd += list(args)
        return subprocess.run(cmd, cwd=str(cwd), env=self.env(), capture_output=True, text=True, timeout=timeout)

    def run_java(self, *args: str, cwd: Path | None = None, timeout: int = 300) -> subprocess.CompletedProcess:
        return subprocess.run(
            [str(self.java), *args],
            cwd=str(cwd) if cwd else None,
            env=self.env(),
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    def run_javac(self, *args: str, cwd: Path | None = None, timeout: int = 300) -> subprocess.CompletedProcess:
        return subprocess.run(
            [str(self.javac), *args],
            cwd=str(cwd) if cwd else None,
            env=self.env(),
            capture_output=True,
            text=True,
            timeout=timeout,
        )


def _candidate_java_homes() -> list[Path]:
    out = []
    for var in ("LTW_JAVA_HOME", "JAVA_HOME"):
        v = os.environ.get(var)
        if v:
            out.append(Path(v))
    exe = shutil.which("javac")
    if exe:
        out.append(Path(exe).resolve().parents[1])
    tools = ROOT.parent / ".tools"
    if tools.is_dir():
        out += sorted(tools.glob("jdk*"), reverse=True)
    return out


def _candidate_mvns() -> list[Path]:
    out = []
    v = os.environ.get("LTW_MAVEN_HOME")
    if v:
        out.append(Path(v) / "bin" / ("mvn.cmd" if os.name == "nt" else "mvn"))
    for name in ("mvn.cmd", "mvn") if os.name == "nt" else ("mvn",):
        exe = shutil.which(name)
        if exe:
            out.append(Path(exe))
    tools = ROOT.parent / ".tools"
    if tools.is_dir():
        for d in sorted(tools.glob("apache-maven*"), reverse=True):
            out.append(d / "bin" / ("mvn.cmd" if os.name == "nt" else "mvn"))
    return out


def find_toolchain() -> Toolchain:
    java_home = next((p for p in _candidate_java_homes() if (p / "bin").is_dir()), None)
    mvn = next((p for p in _candidate_mvns() if p.is_file()), None)
    if java_home is None or mvn is None:
        missing = [n for n, v in (("JDK 17+", java_home), ("Maven 3.9+", mvn)) if v is None]
        raise ToolchainError(
            "cannot find " + " and ".join(missing) + ". Set JAVA_HOME / LTW_MAVEN_HOME, put them on PATH, "
            "or unzip them under ../.tools (jdk-*, apache-maven-*)."
        )
    return Toolchain(java_home=java_home, mvn=mvn)


def toolchain_available() -> bool:
    try:
        find_toolchain()
        return True
    except ToolchainError:
        return False


def describe(tc: Toolchain) -> str:
    return f"java={tc.java_home}  mvn={tc.mvn}  python={sys.version.split()[0]}"
