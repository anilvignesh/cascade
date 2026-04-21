"""
Skills system — pluggable capabilities Cascade can invoke.
Skills live in ~/cascade/skills/<name>/skill.py
Each skill exposes: DESCRIPTION (str) and run(query, context) -> str
"""

import importlib.util, sys
from pathlib import Path

SKILLS_DIR = Path.home() / "cascade" / "skills"

_registry: dict[str, object] = {}


def _load_all():
    if not SKILLS_DIR.exists():
        return
    for skill_dir in SKILLS_DIR.iterdir():
        skill_file = skill_dir / "skill.py"
        if not skill_file.exists():
            continue
        name = skill_dir.name
        if name in _registry:
            continue
        spec = importlib.util.spec_from_file_location(f"skills.{name}", skill_file)
        mod  = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(mod)
            _registry[name] = mod
        except Exception as e:
            print(f"  [skills] failed to load {name}: {e}")


def list_skills() -> dict[str, str]:
    _load_all()
    return {name: getattr(mod, "DESCRIPTION", "no description")
            for name, mod in _registry.items()}


def run_skill(name: str, query: str, context: str = "") -> str:
    _load_all()
    if name not in _registry:
        return f"Unknown skill: {name}. Available: {', '.join(_registry)}"
    mod = _registry[name]
    if not hasattr(mod, "run"):
        return f"Skill '{name}' has no run() function"
    try:
        return mod.run(query, context)
    except Exception as e:
        return f"Skill error: {e}"


def detect_skill(query: str) -> str | None:
    """Return skill name if query starts with /<skillname>."""
    q = query.strip()
    if not q.startswith("/"):
        return None
    name = q.split()[0][1:].lower()
    _load_all()
    return name if name in _registry else None


def skill_exists(name: str) -> bool:
    """Check if a skill is registered (used by route_query validation)."""
    _load_all()
    return name in _registry
