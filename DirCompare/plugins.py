"""
Plugin system for custom scoring signals.

Plugins are Python files placed in:
  - ~/.dircompare/plugins/
  - ./.dircompare/plugins/

Each plugin file must define:
  - name (str): A short identifier
  - weight (int): Score multiplier
  - score(left_files, right_files) -> int: Scoring function

The score function receives two dicts mapping relative paths to FileInfo objects.
Return negative for left-is-newer, positive for right-is-newer, 0 for neutral.
"""

import importlib.util
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

PLUGIN_DIRS = [
    os.path.join(os.path.expanduser("~"), ".dircompare", "plugins"),
    os.path.join(".", ".dircompare", "plugins"),
]


def discover_plugins(extra_dirs: Optional[list[str]] = None, enabled: bool = True):
    """Discover and load plugins from known directories.

    Parameters
    ----------
    extra_dirs : list[str], optional
        Additional directories to search for plugins.
    enabled : bool
        If False, skip plugin discovery entirely and return empty list.

    Returns
    -------
    list
        List of loaded plugin modules.
    """
    if not enabled:
        return []

    search_dirs = list(PLUGIN_DIRS)
    if extra_dirs:
        search_dirs.extend(extra_dirs)

    plugins = []
    seen_names: set[str] = set()

    for dir_path in search_dirs:
        if not os.path.isdir(dir_path):
            continue
        for fname in sorted(os.listdir(dir_path)):
            if not fname.endswith(".py") or fname.startswith("_"):
                continue
            full_path = os.path.join(dir_path, fname)
            plugin = load_plugin(full_path)
            if plugin and getattr(plugin, "name", None) not in seen_names:
                plugins.append(plugin)
                seen_names.add(plugin.name)
    return plugins


def load_plugin(path: str):
    """Load a single plugin from a .py file.

    Returns the loaded module, or None if loading fails.
    """
    try:
        module_name = f"dircompare_plugin_{os.path.basename(path).removesuffix('.py')}"
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            logger.warning("Could not load plugin spec: %s", path)
            return None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # Validate required attributes
        if not hasattr(module, "name"):
            logger.warning("Plugin %s missing 'name' attribute, skipped", path)
            return None
        if not hasattr(module, "weight"):
            logger.warning("Plugin %s missing 'weight' attribute, skipped", path)
            return None
        if not hasattr(module, "score") or not callable(module.score):
            logger.warning("Plugin %s missing callable 'score', skipped", path)
            return None

        return module
    except Exception as e:
        logger.warning("Failed to load plugin %s: %s", path, e)
        return None


def run_plugins(
    plugins: list,
    left_files: dict,
    right_files: dict,
) -> tuple[int, dict[str, int], list[str]]:
    """Execute all plugins and collect score contributions.

    Returns
    -------
    tuple[int, dict[str, int], list[str]]
        (total_score, breakdown_dict, warnings_list)
    """
    total = 0
    breakdown: dict[str, int] = {}
    warnings: list[str] = []

    for plugin in plugins:
        try:
            raw_score = plugin.score(left_files, right_files)
            weighted = raw_score * plugin.weight
            total += weighted
            breakdown[f"plugin:{plugin.name}"] = weighted
        except Exception as e:
            warnings.append(f"Plugin '{plugin.name}' failed: {e}")
            logger.warning("Plugin '%s' raised an error: %s", plugin.name, e)

    return total, breakdown, warnings
