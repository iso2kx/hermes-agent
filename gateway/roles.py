"""
Role-Based Access Control for Gateway Users

Manages tiered permissions (admin/member) for multi-user environments.
Admins get full tool access and can manage users; members get a restricted
toolset suitable for research and analysis.

Storage: ~/.hermes/roles/roles.json
"""

import json
import os
import time
from pathlib import Path
from typing import Optional

ROLES_DIR = Path(os.path.expanduser("~/.hermes/roles"))
ROLES_FILE = ROLES_DIR / "roles.json"

# Available roles, ordered by privilege level
ROLE_ADMIN = "admin"
ROLE_MEMBER = "member"
VALID_ROLES = {ROLE_ADMIN, ROLE_MEMBER}

# Tools restricted from members (dangerous or infrastructure-level)
MEMBER_DENIED_TOOLS = {
    # Terminal & process control
    "terminal", "process",
    # File mutation
    "write_file", "patch",
    # Code execution
    "execute_code",
    # Subagent spawning (cost + risk)
    "delegate_task",
    # Skill management (can alter agent behavior)
    "skill_manage",
    # Home automation
    "ha_call_service",
}

# Tools available to members (safe for research & analysis)
# Everything in _HERMES_CORE_TOOLS minus MEMBER_DENIED_TOOLS
# Plus: read_file, search_files, web, vision, browser (read-only), tts, memory, etc.


def _load_roles() -> dict:
    if ROLES_FILE.exists():
        try:
            return json.loads(ROLES_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_roles(data: dict) -> None:
    ROLES_DIR.mkdir(parents=True, exist_ok=True)
    ROLES_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    try:
        os.chmod(ROLES_FILE, 0o600)
    except OSError:
        pass


def get_role(platform: str, user_id: str) -> Optional[str]:
    """Get a user's role. Returns None if user has no role assigned."""
    roles = _load_roles()
    key = f"{platform}:{user_id}"
    entry = roles.get(key)
    if entry:
        return entry.get("role")
    return None


def set_role(platform: str, user_id: str, role: str,
             user_name: str = "", set_by: str = "") -> bool:
    """Assign a role to a user. Returns True on success."""
    if role not in VALID_ROLES:
        return False
    roles = _load_roles()
    key = f"{platform}:{user_id}"
    roles[key] = {
        "role": role,
        "user_name": user_name,
        "set_by": set_by,
        "set_at": time.time(),
    }
    _save_roles(roles)
    return True


def remove_role(platform: str, user_id: str) -> bool:
    """Remove a user's role. Returns True if found and removed."""
    roles = _load_roles()
    key = f"{platform}:{user_id}"
    if key in roles:
        del roles[key]
        _save_roles(roles)
        return True
    return False


def list_roles(platform: str = None) -> list:
    """List all role assignments, optionally filtered by platform."""
    roles = _load_roles()
    results = []
    for key, entry in roles.items():
        plat, uid = key.split(":", 1)
        if platform and plat != platform:
            continue
        results.append({
            "platform": plat,
            "user_id": uid,
            "role": entry["role"],
            "user_name": entry.get("user_name", ""),
        })
    return results


def is_admin(platform: str, user_id: str) -> bool:
    """Check if a user has admin role."""
    return get_role(platform, user_id) == ROLE_ADMIN


def get_admin_count(platform: str) -> int:
    """Count admins on a platform. Used to prevent removing the last admin."""
    roles = _load_roles()
    count = 0
    for key, entry in roles.items():
        plat, _ = key.split(":", 1)
        if plat == platform and entry.get("role") == ROLE_ADMIN:
            count += 1
    return count


def filter_tools_for_role(tools: list, role: str) -> list:
    """Filter a tool list based on user role. Admins get everything."""
    if role == ROLE_ADMIN:
        return tools
    return [t for t in tools if t not in MEMBER_DENIED_TOOLS]


def ensure_owner_is_admin(platform: str, allowed_users_env: str = "") -> None:
    """Auto-promote users from the allowlist env var to admin if no admins exist.

    Called at gateway startup to ensure there's always at least one admin.
    """
    if get_admin_count(platform) > 0:
        return

    # Promote users from the allowlist
    if allowed_users_env:
        for uid in allowed_users_env.split(","):
            uid = uid.strip()
            if uid:
                set_role(platform, uid, ROLE_ADMIN, set_by="auto:allowlist")
                return
