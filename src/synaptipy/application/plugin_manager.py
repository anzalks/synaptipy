# src/synaptipy/application/plugin_manager.py
# -*- coding: utf-8 -*-
"""
Plugin Manager for synaptipy.

Scans the user plugin directory and, when running from a source checkout or
desktop bundle, an optional example-plugin directory.
Any script using the @AnalysisRegistry.register decorator will automatically
populate the UI and Batch Engine.

Search order:

1. Example plugins: available in source checkouts and desktop bundles, and
   downloadable from the application's Help menu.
2. User plugins: ``~/.synaptipy/plugins/`` - personal, downloaded, or
   third-party additions.

When the same stem name appears in both directories the user's copy takes
precedence and a warning is logged.

This file is part of Synaptipy, licensed under the GNU Affero General Public License v3.0.
See the LICENSE file in the root of the repository for full license details.
"""

import copy
import hashlib
import importlib.resources
import importlib.util
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import QSettings

from synaptipy.shared.constants import APP_NAME, SETTINGS_SECTION

log = logging.getLogger(__name__)

# Default location for 3rd-party user plugins
PLUGIN_DIR = Path.home() / ".synaptipy" / "plugins"

_THIS_FILE = Path(__file__).resolve()


def _get_settings() -> QSettings:
    """Return the canonical application settings namespace."""
    return QSettings(APP_NAME, SETTINGS_SECTION)


@dataclass(frozen=True)
class PluginLoadFailure:
    """A plugin that failed to import without stopping the application."""

    path: Path
    reason: str


def _get_bundled_plugin_dir() -> Optional[Path]:
    """Return an optional example-plugin directory if it exists.

    Tries three strategies in order so the lookup works in all deployment
    The normal pip wheel deliberately does not contain downloadable examples;
    users obtain those through Help -> Download Example Plugins.  Source-tree
    and PyInstaller builds may include examples for development/demo use.
    Returns ``None`` when no optional directory is present.
    """
    # Strategy 0: PyInstaller one-folder bundle
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        candidate = Path(sys._MEIPASS) / "synaptipy" / "examples" / "plugins"
        if candidate.is_dir():
            return candidate

    # Strategy 1: repo / editable-install layout
    # _THIS_FILE is src/synaptipy/application/plugin_manager.py
    # four parents up reaches the repository root
    candidate = _THIS_FILE.parents[3] / "examples" / "plugins"
    if candidate.is_dir():
        return candidate

    # Strategy 2: examples included by a desktop bundle as package data.
    try:
        ref = importlib.resources.files("synaptipy") / "examples" / "plugins"
        resolved = Path(str(ref))
        if resolved.is_dir():
            return resolved
    except (TypeError, FileNotFoundError, AttributeError):
        pass

    log.debug("Optional example plugin dir not found; downloaded plugins remain available.")
    return None


class PluginManager:
    """Manages the discovery, loading, and registration of third-party plugins."""

    @classmethod
    def _ensure_core_registry_snapshot(cls) -> None:
        """Ensure plugin reloads cannot mistake built-ins for plugin entries.

        GUI startup normally creates this snapshot before loading extensions,
        but the CLI, tests, and embedders can invoke the manager directly.
        Without it, disabling plugins removes every registered analysis.
        """
        from synaptipy.core.analysis.registry import AnalysisRegistry

        if AnalysisRegistry._core_analyses:
            return

        import synaptipy.core.analysis  # noqa: F401 - registration side effect

        # Direct callers may already have loaded third-party functions. Only
        # registrations owned by the core package belong in the immutable set.
        AnalysisRegistry._core_analyses = {
            name
            for name, function in AnalysisRegistry._registry.items()
            if getattr(function, "__module__", "").startswith("synaptipy.core.analysis")
        }
        log.debug("Core analysis snapshot ensured: %d entries.", len(AnalysisRegistry._core_analyses))

    @staticmethod
    def _purge_plugin_modules() -> None:
        """Discard dynamically loaded plugin modules before a fresh import."""
        for module_name in list(sys.modules):
            if module_name.startswith("synaptipy_plugin_"):
                sys.modules.pop(module_name, None)
        importlib.invalidate_caches()

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
        ``examples/plugins/`` (if found) and ``~/.synaptipy/plugins/``.

        The user directory takes precedence: if a file with the same stem
        exists in both locations, the examples copy is skipped and a warning
        is emitted so the author knows their local version is active.
        A missing bundled plugin dir is silently ignored.
        """
        bundled_dir = _get_bundled_plugin_dir()
        search_dirs = ([bundled_dir] if bundled_dir is not None else []) + [PLUGIN_DIR]
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
                        "Plugin name collision: '%s' in %s is shadowed by the "
                        "user copy at %s. The user copy will be used.",
                        p_file.name,
                        search_dir,
                        seen_stems[stem],
                    )
                else:
                    seen_stems[stem] = p_file
                    result.append(p_file)

        return result

    @classmethod
    def _load_single_plugin(cls, p_file: Path) -> Optional[PluginLoadFailure]:
        """Attempt to import one plugin file without stopping other plugins."""
        # A plugin can execute registration decorators before a later import or
        # top-level statement fails.  Keep a complete registry snapshot so a
        # reported failure cannot leave a half-loaded analysis visible in the
        # application.
        from synaptipy.core.analysis.registry import AnalysisRegistry

        registry_before = dict(AnalysisRegistry._registry)
        metadata_before = copy.deepcopy(AnalysisRegistry._metadata)
        original_metadata_before = copy.deepcopy(AnalysisRegistry._original_metadata)
        module_name = f"synaptipy_plugin_{p_file.stem}"
        try:
            # Always evict any cached module so @AnalysisRegistry.register
            # decorators fire from the correct file path on every load call.
            # importlib.reload() would re-use the old __spec__ path (which may
            # point to a stale temp directory in tests), so we always do a
            # fresh load instead.
            if module_name in sys.modules:
                del sys.modules[module_name]
            spec = importlib.util.spec_from_file_location(module_name, str(p_file))
            if spec is None or spec.loader is None:
                reason = "Could not create an import specification."
                log.warning("Could not load plugin specification for %s", p_file.name)
                return PluginLoadFailure(p_file, reason)
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
            log.info(f"Successfully loaded plugin: {p_file.name}")
            return None
        except ImportError as e:
            cls._restore_registry_after_failed_plugin(
                AnalysisRegistry, registry_before, metadata_before, original_metadata_before, module_name
            )
            log.error(f"ImportError while loading plugin '{p_file.name}': {e}", exc_info=False)
            return PluginLoadFailure(p_file, f"ImportError: {e}")
        except SyntaxError as e:
            cls._restore_registry_after_failed_plugin(
                AnalysisRegistry, registry_before, metadata_before, original_metadata_before, module_name
            )
            log.error(f"SyntaxError in plugin '{p_file.name}': {e}", exc_info=False)
            return PluginLoadFailure(p_file, f"SyntaxError: {e}")
        except Exception as e:
            cls._restore_registry_after_failed_plugin(
                AnalysisRegistry, registry_before, metadata_before, original_metadata_before, module_name
            )
            log.error(f"Unexpected error loading plugin '{p_file.name}': {e}", exc_info=False)
            return PluginLoadFailure(p_file, f"{type(e).__name__}: {e}")

    @staticmethod
    def _restore_registry_after_failed_plugin(
        registry, registry_before, metadata_before, original_metadata_before, module_name: str
    ) -> None:
        """Restore the analysis registry and discard a partially imported module."""
        registry._registry.clear()
        registry._registry.update(registry_before)
        registry._metadata.clear()
        registry._metadata.update(metadata_before)
        registry._original_metadata.clear()
        registry._original_metadata.update(original_metadata_before)
        sys.modules.pop(module_name, None)

    @classmethod
    def _warn_user_plugins(cls, user_plugin_files: List[Path]) -> bool:
        """Show a one-time security warning when user plugins are about to be loaded.

        User-provided code in ``~/.synaptipy/plugins/`` is executed with the
        same privileges as the running Python process.  This dialog informs the
        user before loading and records acknowledgement in QSettings so it only
        fires once per plugin directory contents hash.

        Args:
            user_plugin_files: List of ``.py`` plugin files from the user directory.

        Returns:
            ``True`` if loading should proceed, ``False`` if the user declined.
        """
        if not user_plugin_files:
            return True

        # Compute a content-based SHA-256 fingerprint of all user plugin files.
        # Hashing *file contents* (not paths) ensures the user is re-prompted
        # whenever a plugin script is modified, even if its filename is unchanged.
        hasher = hashlib.sha256()
        for p in sorted(user_plugin_files, key=lambda f: f.name):
            try:
                hasher.update(p.read_bytes())
            except OSError as exc:
                log.warning("Could not read plugin file for fingerprinting: %s (%s)", p, exc)
        fingerprint = hasher.hexdigest()

        settings = _get_settings()
        acknowledged_key = "plugin_security_acknowledged"
        last_ack = settings.value(acknowledged_key, "", type=str)
        if last_ack == fingerprint:
            return True  # already acknowledged this exact set

        try:
            from PySide6.QtWidgets import QApplication, QMessageBox

            app = QApplication.instance()
            _offscreen = getattr(app, "platformName", lambda: "")() == "offscreen"
            _testing = bool(os.environ.get("PYTEST_CURRENT_TEST"))
            if app is None or _offscreen or _testing:
                # No QApplication yet, headless platform, or pytest session -
                # skip the interactive dialog and proceed automatically.
                log.warning(
                    "Plugin security dialog skipped (no interactive session). "
                    "User plugins will be loaded without confirmation."
                )
                settings.setValue(acknowledged_key, fingerprint)
                return True

            msg = QMessageBox()
            msg.setWindowTitle("Plugin Security Warning")
            msg.setIcon(QMessageBox.Icon.Warning)
            msg.setText("<b>External plugins detected in ~/.synaptipy/plugins/</b>")
            msg.setInformativeText(
                "The following user-provided Python files will be executed with "
                "the same system privileges as Synaptipy:<br><br>"
                + "<br>".join(f"&nbsp;&nbsp;- {p.name}" for p in user_plugin_files)
                + "<br><br>"
                "Only load plugins from sources you trust. "
                "Malicious plugins could modify your data or harm your system."
            )
            msg.setStandardButtons(QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)
            msg.setDefaultButton(QMessageBox.StandardButton.Cancel)
            choice = msg.exec()
            if choice != QMessageBox.StandardButton.Ok:
                log.info("User declined to load external plugins.")
                return False
        except Exception as exc:
            # No display available (headless / CI) - log and proceed.
            log.warning("Plugin security dialog could not be shown (%s); proceeding.", exc)

        settings.setValue(acknowledged_key, fingerprint)
        return True

    @classmethod
    def load_plugins(cls) -> List[PluginLoadFailure]:
        """
        Dynamically imports all plugins discovered by ``get_plugin_files()``.

        Plugins from ``examples/plugins/`` are loaded first, then user plugins.
        A bad plugin (``ImportError``, ``SyntaxError``, or any other exception)
        is skipped gracefully so it does not crash the main application.

        Loading is skipped entirely when the ``enable_plugins`` QSettings key
        is ``False`` (set via Preferences -> Extensions).
        """
        cls._ensure_core_registry_snapshot()

        if not _get_settings().value("enable_plugins", True, type=bool):
            log.info("Plugin loading is disabled via Preferences (enable_plugins=False). Skipping.")
            return []

        cls.create_plugin_directory()
        plugin_files = cls.get_plugin_files()

        if not plugin_files:
            log.debug("No plugins found.")
            return []

        log.info("Discovered %d plugin(s). Attempting to load...", len(plugin_files))

        # Separate user plugins (require security confirmation) from bundled examples.
        user_plugins = [p for p in plugin_files if p.parent.resolve() == PLUGIN_DIR.resolve()]
        if not cls._warn_user_plugins(user_plugins):
            # User declined - load bundled examples only.
            plugin_files = [p for p in plugin_files if p not in user_plugins]
            if not plugin_files:
                log.info("No example plugins to load after user declined external plugins.")
                return []

        # Make both plugin directories importable so plugins can pull in
        # sibling helper modules if they need to.
        bundled_dir = _get_bundled_plugin_dir()
        sys_path_dirs = ([bundled_dir] if bundled_dir is not None else []) + [PLUGIN_DIR]
        for search_dir in sys_path_dirs:
            dir_str = str(search_dir)
            if search_dir.is_dir() and dir_str not in sys.path:
                sys.path.insert(0, dir_str)

        failures = []
        for p_file in plugin_files:
            failure = cls._load_single_plugin(p_file)
            if failure is not None:
                failures.append(failure)

        log.info("Finished loading plugins (%d failed).", len(failures))
        return failures

    @classmethod
    def reload_plugins(cls, enabled: Optional[bool] = None) -> Optional[List[PluginLoadFailure]]:
        """
        Hot-reload plugins without restarting the application.

        Purges all plugin-contributed analyses from ``AnalysisRegistry``,
        then re-loads plugins if the ``enable_plugins`` setting is ``True``.
        Call this after the user toggles the "Enable Custom Plugins" preference,
        then rebuild the Analyser UI to reflect the change. Returns ``None``
        when the user cancels the security confirmation, signalling callers to
        preserve the current UI.
        """
        from synaptipy.core.analysis.registry import AnalysisRegistry

        cls._ensure_core_registry_snapshot()

        if enabled is None:
            enabled = _get_settings().value("enable_plugins", True, type=bool)

        if not enabled:
            AnalysisRegistry.unregister_plugins()
            cls._purge_plugin_modules()
            log.info("Plugin reload: enable_plugins is False - plugins will not be re-loaded.")
            return []

        cls.create_plugin_directory()
        plugin_files = cls.get_plugin_files()

        if not plugin_files:
            log.debug("No plugins found during hot-reload.")
            AnalysisRegistry.unregister_plugins()
            return []

        # Confirm changed user code *before* discarding working registrations.
        # Cancelling the warning therefore leaves the existing UI untouched.
        user_plugins = [p for p in plugin_files if p.parent.resolve() == PLUGIN_DIR.resolve()]
        if not cls._warn_user_plugins(user_plugins):
            log.info("Plugin reload cancelled; keeping the currently loaded plugins.")
            return None

        AnalysisRegistry.unregister_plugins()
        cls._purge_plugin_modules()
        log.debug("Plugin analyses unregistered for hot-reload.")

        log.info("Hot-reloading %d plugin(s)...", len(plugin_files))

        # ``load_plugins`` repeats the fingerprint comparison, but it now
        # matches the acknowledgement above and performs the common import and
        # error-reporting path used by GUI, CLI, and worker processes.
        failures = cls.load_plugins()
        log.info("Hot-reload complete (%d failed).", len(failures))
        return failures
