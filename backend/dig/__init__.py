"""DIG package init — version is read from package metadata so
``backend/pyproject.toml`` stays the single source of truth.

The previous form (``__version__ = "0.5.0"``) drifted away from
pyproject's declared version every time someone bumped one and forgot the
other. ``importlib.metadata.version("dig")`` reads from the installed
distribution's metadata, which is generated from pyproject.toml at install
time, so a fresh ``pip install -e .`` makes the bump propagate
automatically to /health, the home-page badge, and Settings → About.

When the package is imported from a source tree without an installed
distribution (rare in dev — usually the venv has it editable-installed),
``PackageNotFoundError`` is raised; we fall back to "0.0.0+unknown" rather
than crashing module import. CI and tests would otherwise fail in
confusing ways before any actual error surfaces.
"""

from importlib.metadata import PackageNotFoundError, version as _pkg_version

try:
    __version__ = _pkg_version("dig")
except PackageNotFoundError:
    __version__ = "0.0.0+unknown"
