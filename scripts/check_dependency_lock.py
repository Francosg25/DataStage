"""Check exact Python pins against pyproject and the installed validation environment."""
import re
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import tomllib
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name


def check(root: Path) -> tuple[int, list[str]]:
    locked = {}
    errors = []
    for line in (root / "backend/requirements.lock").read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        match = re.fullmatch(r"([A-Za-z0-9_.-]+)==([^\s;]+)", line)
        if not match:
            errors.append("Every lock entry must be an exact package==version pin: " + line)
            continue
        name, pinned = canonicalize_name(match[1]), match[2]
        if name in locked:
            errors.append("Duplicate lock entry: " + name)
        locked[name] = pinned
        try:
            installed = version(name)
            if installed != pinned:
                errors.append(f"{name}: installed {installed}, lock requires {pinned}")
        except PackageNotFoundError:
            errors.append("Missing installed dependency: " + name)
    project = tomllib.loads((root / "backend/pyproject.toml").read_text(encoding="utf-8"))["project"]
    requirements = project["dependencies"] + project["optional-dependencies"]["test"]
    for declaration in requirements:
        requirement = Requirement(declaration)
        name = canonicalize_name(requirement.name)
        if name not in locked or not requirement.specifier.contains(locked[name]):
            errors.append("Lock does not satisfy pyproject: " + declaration)
    return len(locked), errors


if __name__ == "__main__":
    count, errors = check(Path(__file__).resolve().parents[1])
    if errors:
        sys.exit("\n".join(errors))
    print(f"Python lock verified: {count} exact versions; project and test dependencies satisfied.")
