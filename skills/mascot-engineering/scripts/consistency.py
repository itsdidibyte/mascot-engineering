#!/usr/bin/env python3
"""G1 cross-view consistency: do the reference views describe ONE 3D character?

    python consistency.py WORKSPACE [--tol 0.03]

Run after silhouettes.py. Checks (all in units of character height):
  1. front vs back width profile  (same object seen from opposite sides -> equal widths)
  2. left vs right depth profile
  3. feature heights: necks/waists (width minima) and bulges (maxima) must sit at the
     same height in front and side views. AI-generated turnarounds often fail this.
  4. front left/right asymmetry bands (tells you where mirroring parts is NOT safe)
Writes 02_views/CONSISTENCY.json, CONSISTENCY.md and TURNAROUND.png
(all views side by side on identical height guides: the fastest human check).
Exit code 0 = no CONFLICT; 3 = at least one CONFLICT needing an owner decision.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

from mascot_lib import analysis, drawing, silhouette  # noqa: E402
from mascot_lib.workspace import append_issue, load_spec, save_json, view_by_kind  # noqa: E402


def load_profile(ws, v):
    p = ws / "02_views" / f"{v['id']}_profile.json"
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))["stations"]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("workspace", type=Path)
    ap.add_argument("--tol", type=float, default=0.03, help="tolerance in character heights (default 0.03)")
    a = ap.parse_args(argv)
    ws = a.workspace.resolve()
    spec, spec_file = load_spec(ws)
    H = float(spec["scale"]["character_height"])
    tol = a.tol * H
    views = {k: view_by_kind(spec, k) for k in ("front", "back", "left", "right")}
    profs = {k: (load_profile(ws, v) if v else None) for k, v in views.items()}
    result = {"tolerance_units": tol, "checks": []}
    worst = "CONSISTENT"

    def rank(s):
        return {"CONSISTENT": 0, "CHECK": 1, "CONFLICT": 2, "NOT_TESTED": -1}[s]

    def add(name, status, detail):
        nonlocal worst
        result["checks"].append({"check": name, "status": status, **detail})
        if rank(status) > rank(worst):
            worst = status

    for a_k, b_k, label in (("front", "back", "width"), ("left", "right", "depth")):
        if profs[a_k] and profs[b_k]:
            z, _, _, wa = analysis.widths(profs[a_k])
            _, _, _, wb = analysis.widths(profs[b_k])
            d = np.nan_to_num(wb) - np.nan_to_num(wa)
            bd = analysis.bands(z, d, tol)
            mx = float(np.nanmax(np.abs(d)))
            status = "CONSISTENT" if not bd else ("CONFLICT" if mx > 2 * tol else "CHECK")
            add(f"{a_k}_vs_{b_k}_{label}", status, {"max_abs_diff": round(mx, 4), "bands": bd})
        else:
            add(f"{a_k}_vs_{b_k}_{label}", "NOT_TESTED", {"reason": "view missing"})

    wide = profs["front"] or profs["back"]
    wide_kind = "front" if profs["front"] else "back"
    side = profs["right"] or profs["left"]
    side_kind = "right" if profs["right"] else "left"
    if wide and side:
        z, _, _, ww = analysis.widths(wide, "main")
        _, _, _, wd = analysis.widths(side, "main")
        ea = silhouette.extrema(z, np.nan_to_num(ww), prominence=0.02 * H)
        eb = silhouette.extrema(z, np.nan_to_num(wd), prominence=0.02 * H)
        pairs = analysis.match_extrema(ea, eb, tol)
        n_check = sum(p["status"] == "CHECK" for p in pairs)
        bad = [p for p in pairs if p["status"] == "CHECK" and abs(p["dz"]) > 2 * tol]
        status = "CONFLICT" if bad else ("CHECK" if n_check else "CONSISTENT")
        add(f"feature_heights_{wide_kind}_vs_{side_kind}", status,
            {"extrema_width_view": ea, "extrema_depth_view": eb, "pairs": pairs,
             "note": "UNMATCHED extrema are normal (a belly bulge is visible only from the side)."})
    else:
        add("feature_heights", "NOT_TESTED", {"reason": "need a front/back and a side view"})

    if profs["front"]:
        z, l, r, _ = analysis.widths(profs["front"])
        asym = r + l  # 0 when symmetric about h=0
        bd = analysis.bands(z, asym, tol)
        add("front_left_right_symmetry", "CONSISTENT" if not bd else "CHECK",
            {"bands": bd, "note": "Positive = sticks out more on image-right (+X, character's LEFT). Do not mirror parts in these bands without an owner decision."})

    result["overall"] = worst
    save_json(ws / "02_views" / "CONSISTENCY.json", result)
    md = [f"# Cross-view consistency: **{worst}**", "", f"Tolerance: {tol:.3f} units ({a.tol:.0%} of height).", ""]
    for c in result["checks"]:
        md.append(f"## {c['check']}: {c['status']}")
        for k in ("max_abs_diff", "reason", "note"):
            if k in c:
                md.append(f"- {k}: {c[k]}")
        for b in c.get("bands", []):
            md.append(f"- z {b['z_from']:.2f}-{b['z_to']:.2f} ({analysis.region_name(b['z_from'], H)}): worst {b['worst']}")
        for p in c.get("pairs", []):
            md.append(f"- {p['kind']} at z={p['z_a']} vs {p['z_b']} (dz={p['dz']}): {p['status']}")
        md.append("")
    md += ["## What to do", "- CONSISTENT: proceed to G2.",
           "- CHECK: look at TURNAROUND.png; the owner decides if the difference is real design or drawing drift.",
           "- CONFLICT: ask the owner which view is canonical for the listed heights; record it in DECISIONS.md. Do not average."]
    (ws / "02_views" / "CONSISTENCY.md").write_text("\n".join(md) + "\n", encoding="utf-8")

    sheet_imgs, labels = [], []
    for k in ("front", "right", "back", "left"):
        v = views[k]
        p = ws / "02_views" / f"{v['id']}_overlay.png" if v else None
        if p and p.exists():
            im = Image.open(p)
            sheet_imgs.append(im.resize((im.width // 2, im.height // 2), Image.LANCZOS))
            labels.append(f"{v['id']} ({k})")
    if sheet_imgs:
        drawing.contact_sheet(sheet_imgs, labels).save(ws / "02_views" / "TURNAROUND.png")
    if worst == "CONFLICT":
        append_issue(spec, "G1", "blocking", "Reference views disagree (see 02_views/CONSISTENCY.md). Owner must choose the canonical view per region.")
        save_json(spec_file, spec)
    print(f"CONSISTENCY: {worst}  -> 02_views/CONSISTENCY.md, TURNAROUND.png")
    return 3 if worst == "CONFLICT" else 0


if __name__ == "__main__":
    sys.exit(main())
