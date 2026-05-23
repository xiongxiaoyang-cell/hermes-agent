"""
Wrapper for hermes-user-memory probe module.

Loads probe.py directly via importlib (no __init__.py required in skills/).
Uses 'probe' as the module name consistently to avoid circular import issues.

All attribute accesses are delegated to the underlying probe module via
__getattr__, so that lazy-initialized singletons (e.g. _default_manager)
are always fetched live after get_manager() has run.
"""

import importlib
import os
import sys

_HERMES_ROOT = os.path.expanduser("~/.hermes")
_PROBE_PATH = os.path.join(
    _HERMES_ROOT, "memories", "hermes-user-memory", "skills", "probe.py"
)
_MOD_NAME = "probe"

if _MOD_NAME not in sys.modules:
    _spec = importlib.util.spec_from_file_location(_MOD_NAME, _PROBE_PATH)
    _loader = _spec.loader
    _module = importlib.util.module_from_spec(_spec)
    sys.modules[_MOD_NAME] = _module
    _loader.exec_module(_module)

_m = sys.modules[_MOD_NAME]


def __getattr__(name):
    """Delegate all attribute access to the underlying probe module so that
    lazily-initialized module-level objects (e.g. _default_manager) are
    fetched only after they have been created by get_manager()."""
    return getattr(_m, name)


__all__ = [
    "ProbeManager",
    "ProbeConfig",
    "trigger_probe",
    "check_triggers",
    "record_probe_response",
    "PROBE_TEMPLATES",
    "Probe",
    "TriggerDetector",
]
