"""
app/services/asset_bundler.py
==============================
Concatenates the app's own JS and CSS files into single bundles at process
startup, so the browser makes 2 requests instead of 26 (see Code-Audit.md,
finding I3). This project's only "deploy" step is restarting the process
(`python server.py`) -- there's no separate build pipeline -- so the bundle
is regenerated fresh every startup instead of being a committed artifact
that could go stale.

Vendor scripts (purify.min.js, marked.min.js) stay as separate <script defer>
tags in _head.html; only the app's own source files are bundled here.

Order matters: these lists must match the <link>/<script> order in
templates/partials/index/_head.html and _scripts.html exactly. Concatenation
preserves that order, so behavior is identical to loading the files
separately -- classic (non-module) <script> tags already share one global
scope and execute in document order, so merging them into one file changes
nothing about how the code runs.
"""

import os

JS_SOURCES = [
    "static/js/utils.js",
    "static/js/benchmarks.js",
    "static/js/state.js",
    "static/js/ui/config.js",
    "static/js/ui/lobby.js",
    "static/js/ui/animation.js",
    "static/js/ui/setup.js",
    "static/js/ui/table.js",
    "static/js/ui/table-modals.js",
    "static/js/ui/table-render.js",
    "static/js/ui/log.js",
    "static/js/ui/kpi.js",
    "static/js/ui/trivia.js",
    "static/js/ui/admin.js",
    "static/js/ui/admin-settings.js",
    "static/js/ui/bootstrap.js",
    "static/js/app.js",
]
JS_BUNDLE = "static/js/bundle.js"

CSS_SOURCES = [
    "static/css/main.css",
    "static/css/components/table.css",
    "static/css/components/log.css",
    "static/css/components/kpi.css",
    "static/css/components/controls.css",
    "static/css/components/modals.css",
    "static/css/components/lobby.css",
    "static/css/components/tabs.css",
    "static/css/components/utilities.css",
]
CSS_BUNDLE = "static/css/bundle.css"


def _concat(root: str, sources: list[str], dest_rel: str) -> None:
    chunks = []
    for rel in sources:
        with open(os.path.join(root, rel), "r", encoding="utf-8") as f:
            chunks.append(f"/* ==== {rel} ==== */\n" + f.read())
    with open(os.path.join(root, dest_rel), "w", encoding="utf-8") as f:
        f.write("\n\n".join(chunks))


def build_bundles(root: str) -> None:
    """Regenerate static/js/bundle.js and static/css/bundle.css from source."""
    _concat(root, JS_SOURCES, JS_BUNDLE)
    _concat(root, CSS_SOURCES, CSS_BUNDLE)
