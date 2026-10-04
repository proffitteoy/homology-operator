"""Public documentation: the same Sphinx/MyST/Furo layout as Topp."""

import re
from html import escape
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

project = "homology-operator"
author = "homology-operator contributors"
copyright = "2026, homology-operator contributors"
release = "0.0.2.dev0"
language = "zh_CN"
extensions = ["myst_parser", "sphinx.ext.mathjax", "sphinx_copybutton"]
source_suffix = {".md": "markdown"}
root_doc = "index"
exclude_patterns = [
    "_build",
    "en/**",
    "research/**",
    "development/**",
    "README.md",
    "冷启动.md",
    "PHASE*_REPORT.md",
    "BENCHMARKS.md",
    "FIXTURES.md",
    "S4_*.md",
    "S5_*.md",
]
myst_enable_extensions = ["colon_fence", "dollarmath", "fieldlist", "substitution"]
myst_dmath_double_inline = True
myst_heading_anchors = 4
html_theme = "furo"
html_title = "homology-operator 中文文档"
html_static_path = []
html_theme_options = {
    "source_repository": "https://github.com/proffitteoy/homology-operator/",
    "source_branch": "main",
    "source_directory": "docs/",
    "light_css_variables": {
        "color-brand-primary": "#1f5f79",
        "color-brand-content": "#1f5f79",
    },
    "dark_css_variables": {
        "color-brand-primary": "#6cb6d4",
        "color-brand-content": "#6cb6d4",
    },
}
copybutton_prompt_text = r">>> |\.\.\. |\$ "
copybutton_prompt_is_regexp = True


def prepare_markdown(app, docname, source):
    """Render legacy math and resolve evidence/cross-language links at build time."""
    docs = Path(__file__).resolve().parent
    root = docs.parent
    srcdir = Path(app.srcdir).resolve()
    document = srcdir / (docname + ".md")

    def repository_link(match):
        target = urlsplit(match[2])
        if target.scheme or target.netloc or not target.path:
            return match[0]
        path = (document.parent / unquote(target.path)).resolve()
        if not path.is_relative_to(root) or not path.exists():
            return match[0]
        if path.is_relative_to(srcdir):
            local = path.relative_to(srcdir).as_posix()
            if path.suffix == ".md" and local[:-3] in app.env.found_docs:
                return match[0]
        counterpart = docs if app.config.language == "en" else docs / "en"
        if path.suffix == ".md" and path.is_relative_to(counterpart):
            local = path.relative_to(counterpart).as_posix()
            public = {
                "index.md",
                "INTERFACE.md",
                "RESULT_MODEL.md",
                "ARCHITECTURE.md",
                "SOLVER_CONTRACT.md",
                "VALIDATION.md",
                "platforms.md",
                "USAGE.md",
            }
            if local in public or local.startswith(("getting-started/", "guide/")):
                url = target.path[:-3] + ".html"
                if target.fragment:
                    url += "#" + target.fragment
                return (
                    f'<a href="{escape(url, quote=True)}">{escape(match[1][1:-1])}</a>'
                )
        kind = "tree" if path.is_dir() else "blob"
        relative = quote(path.relative_to(root).as_posix())
        url = f"https://github.com/proffitteoy/homology-operator/{kind}/main/{relative}"
        if target.fragment:
            url += "#" + target.fragment
        return f"{match[1]}({url})"

    parts = re.split(r"(^```[^\n]*\n.*?^```[ \t]*$)", source[0], flags=re.M | re.S)
    for index in range(0, len(parts), 2):
        prose = re.sub(
            r"\\\[\s*\n(.*?)\n\s*\\\]", r"$$\n\1\n$$", parts[index], flags=re.S
        )
        prose = re.sub(r"\\\((.*?)\\\)", r"$\1$", prose)
        parts[index] = re.sub(r"(\[[^\]\n]*\])\(([^)\n]+)\)", repository_link, prose)
    source[0] = "".join(parts)


def setup(app):
    app.connect("source-read", prepare_markdown)
