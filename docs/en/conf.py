"""English build with shared theme and link handling."""

from pathlib import Path
import runpy

_shared_config = runpy.run_path(str(Path(__file__).resolve().parents[1] / "conf.py"))
globals().update(_shared_config)
language = "en"
exclude_patterns = ["_build"]
html_title = "homology-operator documentation"
html_theme_options = dict(
    _shared_config["html_theme_options"], source_directory="docs/en/"
)

html_baseurl = "https://proffitteoy.github.io/homology-operator/"
