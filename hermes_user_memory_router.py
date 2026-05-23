"""
Thin wrapper that exposes the preference router from hermes-user-memory.

Import path: from hermes_user_memory_router import route, RouteResult
Actual impl:   ~/.hermes/memories/hermes-user-memory/skills/router.py
"""
import os
import sys

_HERMES_HOME = os.environ.get(
    "HERMES_HOME",
    os.path.join(os.path.expanduser("~"), ".hermes"),
)
_router_path = os.path.join(
    _HERMES_HOME, "memories", "hermes-user-memory", "skills", "router.py"
)

if _router_path not in sys.path:
    sys.path.insert(0, os.path.dirname(os.path.dirname(_router_path)))

from skills.router import route, RouteResult  # noqa: E402, F401
