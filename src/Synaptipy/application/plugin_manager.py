# src/Synaptipy/application/plugin_manager.py
# -*- coding: utf-8 -*-
"""
Plugin Manager for Synaptipy.

Scans two plugin directories and dynamically loads external Python scripts.
Any script using the @AnalysisRegistry.register decorator will automatically
populate the UI and Batch Engine.

Search order:

1. Built-in examples: ``<project_root>/examples/plugins/`` - shipped with the
   package so features work out-of-the-box.
2. User plugins: ``~/.synaptipy/plugins/`` - personal or third-party additions.

When the same stem name appears in both directories the user's copy takes
precedence and a warning is logged.

This file is part of Synaptipy, licensed under the GNU Affero General Public License v3.0.
See the LICENSE file in the root of the repository for full license details.
"""

import importlib.util
import logging
import sys
from pathlib import Path
from typing import List

from PySide6.QtCore import QSettings

log = logging.getLogger(__name__)

# Default location for 3rd-party user plugins
PLUGIN_DIR = Path.home() / ".synaptipy" / "plugins"

# Built-in example plugins shipped alongside the source tree.
# Resolved relative to this file: src/Synaptipy/application/ -> project_root
_THIS_FILE = Path(__file__).resolve()
_PROJECT_ROOT = _THIS_FILE.parents[3]  # src/Synaptipy/application -> project root
EXAMPLES_PLUGIN_DIR = _PROJECT_ROOT / "examples" / "plugins"


class PluginManager:
    """Manages the discovery, loading, and registration of third-party plugins."""

    @classmethod
    def create_plugin_directory(cls):
        """Ensures the user plugin directory exists."""
        try:
            PLUGIN_DIR.mkdir(parents=True, exist_ok=True)
            log.debug(f"Plugin directory verified at: {PLUGIN_DIR}")
        except Exception as e:
            log.error(f"Failed to create plugin directory {PLUGIN_DIR}: {e}")

    @classmethod
    def get_plugin_files(cls) -> List[Path]:
        """
        Returns a deduplicated list of plugin ``.py`` files from both
        ``examples/plugins/`` and ``~/.synaptipy/plugins/``.

        The user directory takes precedence: if a file with the same stem
        exists in both locations, the examples copy is skipped and a warning
        is emitted so the author knows their local version is active.
        """
        search_dirs = [EXAMPLES_PLUGIN_DIR, PLUGIN_DIR]
        seen_stems: dict = {}  # stem -> Path that claimed it first (user wins)
        result: List[Path] = []

        # Collect user plugins first so they shadow examples
        for search_dir in reversed(search_dirs):
            if not (search_dir.exists() and search_dir.is_dir()):
                continue
            for p_file in sorted(search_dir.glob("*.py")):
                if p_file.name == "__init__.py":
                    continue
                stem = p_file.stem
                if stem in seen_stems:
                    log.warning(
                        f"Plugin name collision: '{p_file.name}' in {search_dir} "
                        f"is shadowed by the user copy at {seen_stems[stem]}. "
                        "The user copy will be used."
                    )
                else:
                    seen_stems[stem] = p_file
                    result.append(p_file)

        return result

    @classmethod
    def _load_single_plugin(cls, p_file: Path) -> None:
        """Attempt to import one plugin file and log any failure gracefully."""
        module_name = f"synaptipy_plugin_{p_file.stem}"
        try:
            if module_name in sys.modules:
                # Module already loaded — force a reload so the
                # @AnalysisRegistry.register decorators fire again.
                importlib.reload(sys.modules[module_name])
            else:
                spec = importlib.util.spec_from_file_location(module_name, str(p_file))
                if spec is None or spec.loader is None:
                    log.warning(f"Could not load plugin specification for {p_file.name}")
                    return
                module = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = module
                spec.loader.exec_module(module)
            log.info(f"Successfully loaded plugin: {p_file.name}")
        except ImportError as e:
            log.error(f"ImportError while loading plugin '{p_file.name}': {e}", exc_info=False)
        except SyntaxError as e:
            log.error(f"SyntaxError in plugin '{p_file.name}': {e}", exc_info=False)
        except Exception as e:
            log.error(f"Unexpected error loading plugin '{p_file.name}': {e}", exc_info=False)

    @classmethod
    def load_plugins(cls):
        """
        Dynamically imports all plugins discovered by ``get_plugin_files()``.

        Plugins from ``examples/plugins/`` are loaded first, then user plugins.
        A bad plugin (``ImportError``, ``SyntaxError``, or any other exception)
        is skipped gracefully so it does not crash the main application.

        Loading is skipped entirely when the ``enable_plugins`` QSettings key
        is ``False`` (set via Preferences -> Extensions).
        """
        if not QSettings().value("enable_plugins", True, type=bool):
            log.info("Plugin loading is disabled via Preferences (enable_plugins=False). Skipping.")
            return

        cls.create_plugin_directory()
        plugin_files = cls.get_plugin_files()

        if not plugin_files:
            log.debug("No plugins found.")
            return

        log.info(f"Discovered {len(plugin_files)} plugin(s). Attempting to load...")

        # Make both plugin directories importable so plugins can pull in
        # sibling helper modules if they need to.
        for search_dir in (EXAMPLES_PLUGIN_DIR, PLUGIN_DIR):
            dir_str = str(search_dir)
            if search_dir.is_dir() and dir_str not in sys.path:
                sys.path.insert(0, dir_str)

        for p_file in plugin_files:
            cls._load_single_plugin(p_file)

        log.info("Finished loading plugins.")

    @classmethod
    def reload_plugins(cls):
        """
        Hot-reload plugins without restarting the application.

        Purges all plugin-contributed analyses from ``AnalysisRegistry``,
        then re-loads plugins if the ``enable_plugins`` setting is ``True``.
        Call this after the user toggles the "Enable Custom Plugins" preference,
        then rebuild the Analyser UI to reflect the change.
        """
        from Synaptipy.core.analysis.registry import AnalysisRegistry

        AnalysisRegistry.unregister_plugins()
        log.debug("Plugin analyses unregistered for hot-reload.")

        if not QSettings().value("enable_plugins", True, type=bool):
            log.info("Plugin reload: enable_plugins is False — plugins will not be re-loaded.")
            return

        cls.create_plugin_directory()
        plugin_files = cls.get_plugin_files()

        if not plugin_files:
            log.debug("No plugins found during hot-reload.")
            return

        log.info(f"Hot-reloading {len(plugin_files)} plugin(s)...")

        for search_dir in (EXAMPLES_PLUGIN_DIR, PLUGIN_DIR):
            dir_str = str(search_dir)
            if search_dir.is_dir() and dir_str not in sys.path:
                sys.path.insert(0, dir_str)

        for p_file in plugin_files:
            cls._load_single_plugin(p_file)

        log.info("Hot-reload complete.")
