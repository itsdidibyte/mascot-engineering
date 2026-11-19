"""Character workspace layout, spec I/O and hashing helpers (stdlib only)."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

FOLDERS = ("00_intake", "01_references", "02_views", "03_geometry", "04_build",
           "05_validation", "06_surface_motion")
SPEC_REL = Path("04_build") / "build_spec.json"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def spec_path(ws: Path) -> Path:
    return Path(ws) / SPEC_REL


def load_spec(ws_or_spec: Path) -> tuple[dict, Path]:
    p = Path(ws_or_spec)
    if p.is_dir():
        p = spec_path(p)
    return json.loads(p.read_text(encoding="utf-8")), p


def save_json(path: Path, data) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def workspace_of(spec_file: Path) -> Path:
    spec_file = Path(spec_file).resolve()
    if spec_file.parent.name == "04_build":
        return spec_file.parent.parent
    return spec_file.parent


def geometry_hash(spec: dict) -> str:
    """Hash of everything that affects built geometry/appearance.

    Excludes bookkeeping that legitimately changes after a build (package_mode,
    release_evidence, decisions, unresolved_issues, notes) so a build log can be
    matched against the current spec without a chicken-and-egg problem.
    """
    s = copy.deepcopy(spec)
    for k in ("package_mode", "release_evidence", "decisions", "unresolved_issues", "notes"):
        s.pop(k, None)
    blob = json.dumps(s, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def view_by_kind(spec: dict, kind: str, role: str = "canonical"):
    for v in spec.get("views", []):
        if v["kind"] == kind and v.get("role", "canonical") == role:
            return v
    return None


def append_issue(spec: dict, gate: str, severity: str, text: str) -> None:
    issues = spec.setdefault("unresolved_issues", [])
    for i in issues:
        if isinstance(i, dict) and i.get("text") == text:
            return
    issues.append({"id": f"ISSUE-{len(issues) + 1:03d}", "gate": gate, "severity": severity, "text": text})
