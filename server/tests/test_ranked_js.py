"""Test the plural() helper in ranked.js by running it with node (if available).

The plural() logic is JavaScript in ``server/static/ranked.js``; there is no
browser in the test environment, but node can load the file (the IIFE only
touches ``window`` at load time) and we can call the exposed ``window.rankedPlural``.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from server.ranked_rules import DEFAULT_TIERS
from mcsu_gui.tabs.ranked_view import TIER_COLORS, TIER_SHAPES

JS_PATH = Path(__file__).resolve().parents[1] / "static" / "ranked.js"

NODE = shutil.which("node")

# (n, expected form index into ["игра", "игры", "игр"])
CASES = [
    (1, 0), (2, 1), (3, 1), (4, 1), (5, 2), (10, 2),
    (11, 2), (12, 2), (13, 2), (14, 2),
    (21, 0), (22, 1), (25, 2),
    (101, 0), (102, 1), (104, 1), (105, 2),
    (111, 2), (112, 2), (114, 2),
    (0, 2), (100, 2),
]


@pytest.mark.skipif(NODE is None, reason="node not available")
def test_ranked_js_plural():
    cases_js = json.dumps([[n, idx] for n, idx in CASES], separators=(",", ":"))
    script = (
        "global.window = {};\n"
        "require(" + json.dumps(str(JS_PATH)) + ");\n"
        "const plural = window.rankedPlural;\n"
        "const forms = ['a','b','c'];\n"
        "for (const [n, idx] of " + cases_js + ") {\n"
        "  const got = plural(n, forms);\n"
        "  if (got !== forms[idx]) {\n"
        "    console.error('plural(' + n + ') = ' + got + ', expected ' + forms[idx]);\n"
        "    process.exit(1);\n"
        "  }\n"
        "}\n"
        "console.log('plural OK');\n"
    )
    r = subprocess.run([NODE, "-e", script], capture_output=True, text=True)
    assert r.returncode == 0, f"plural() failed:\n{r.stderr}"


@pytest.mark.skipif(NODE is None, reason="node not available")
def test_ranked_js_star_window_and_tier_shapes():
    """Window text, tier colours/shapes and sub-rank figures come from the server."""
    names = [tier.name for tier in DEFAULT_TIERS]
    names_js = json.dumps(names, ensure_ascii=False)
    colors_js = json.dumps(TIER_COLORS, ensure_ascii=False)
    shapes_js = json.dumps(TIER_SHAPES, ensure_ascii=False)
    script = (
        "global.window = {};\n"
        "require(" + json.dumps(str(JS_PATH)) + ");\n"
        "const win = window.rankedStarWindowText;\n"
        "if (win({min: 5.35, max: 5.65, target: 5.5}) !== '5.35–5.65★') {\n"
        "  console.error('window text mismatch'); process.exit(1);\n"
        "}\n"
        "if (win(null) !== '' || win({}) !== '') {\n"
        "  console.error('window must be empty without server data'); process.exit(1);\n"
        "}\n"
        "const names = " + names_js + ";\n"
        "const expectedColors = " + colors_js + ";\n"
        "const expectedShapes = " + shapes_js + ";\n"
        "const colors = window.rankedTierColors;\n"
        "const shapes = window.rankedTierShapes;\n"
        "for (const name of names) {\n"
        "  if (colors[name] !== expectedColors[name]) {\n"
        "    console.error('color mismatch: ' + name); process.exit(1);\n"
        "  }\n"
        "  if (shapes[name] !== expectedShapes[name]) {\n"
        "    console.error('shape mismatch: ' + name); process.exit(1);\n"
        "  }\n"
        "  const svg = window.rankedTierShapeSvg(name, true, 20);\n"
        "  if (!svg.includes('viewBox=\"0 0 16 16\"') || !svg.includes(colors[name])) {\n"
        "    console.error('bad figure: ' + name); process.exit(1);\n"
        "  }\n"
        "}\n"
        "if (Object.keys(colors).length !== names.length || Object.keys(shapes).length !== names.length) {\n"
        "  console.error('stale tier keys'); process.exit(1);\n"
        "}\n"
        "const sub = window.rankedSubRankHtml;\n"
        "const html = sub({filled: 2, total: 4}, 'Алмаз');\n"
        "if ((html.match(/<svg/g) || []).length !== 4) {\n"
        "  console.error('total figures mismatch'); process.exit(1);\n"
        "}\n"
        "if ((html.match(/fill=\"#7dd3fc\"/g) || []).length !== 2) {\n"
        "  console.error('filled figures mismatch'); process.exit(1);\n"
        "}\n"
        "if ((html.match(/fill=\"#1f2347\"/g) || []).length !== 2) {\n"
        "  console.error('empty figures mismatch'); process.exit(1);\n"
        "}\n"
        "const marker = sub(null, 'Легенда');\n"
        "if ((marker.match(/<svg/g) || []).length !== 1 || !marker.includes('<circle')) {\n"
        "  console.error('null sub_rank marker mismatch'); process.exit(1);\n"
        "}\n"
        "for (let f = 1; f <= 4; f++) {\n"
        "  const states = window.rankedShapeStates({filled: f, total: 4});\n"
        "  if (states.length !== 4 || states.filter(Boolean).length !== f) {\n"
        "    console.error('shape states mismatch at ' + f); process.exit(1);\n"
        "  }\n"
        "}\n"
        "console.log('star window and tier shapes OK');\n"
    )
    r = subprocess.run([NODE, "-e", script], capture_output=True, text=True)
    assert r.returncode == 0, f"star window / tier shapes failed:\n{r.stderr}"
