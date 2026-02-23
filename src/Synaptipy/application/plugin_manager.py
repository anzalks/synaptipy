# src/Synaptipy/application/plugin_manager.py
# -*- coding: utf-8 -*-
"""
Plugin Manager for Synaptipy.

Scans the user's plugin directory (`~/.synaptipy/plugins/`) and dynamically
loads external Python scripts. Any script using the @AnalysisRegistry.register
decorator will automatically populate the UI and Batch Engine.

This file is part of Synaptipy, licensed under the GNU Affero General Public License v3.0.
See the LICENSE file in the root of the repository for full license details.
"""

import logging
import importlib.util
import sys
from pathlib import Path
from typing import List

log = logging.getLogger(__name__)

# Default location for 3rd-party user plugins
PLUGIN_DIR = Path.home() / ".synaptipy" / "plugins"

class PluginManager:
    """Manages the discovery, loading, and registration of third-party plugins."""

    @classmethod
    def create_plugin_directory(cls):
        """Ensures the plugin directory exists."""
        try:
            PLUGIN_DIR.mkdir(parents=True, exist_ok=True)
            log.debug(f"Plugin directory verified at: {PLUGIN_DIR}")
        except Exception as e:
            log.error(f"Failed to create plugin directory {PLUGIN_DIR}: {e}")

    @classmethod
    def get_plugin_files(cls) -> List[Path]:
        """Returns a list of all .py files in the plugin directory."""
        if not PLUGIN_DIR.exists():
            return []
        
        # Only loading top-level python files for safety and simplicity
        plugin_files = list(PLUGIN_DIR.glob("*.py"))
        # Exclude __init__.py if it exists
        return [f for f in plugin_files if f.name != "__init__.py"]

    @classmethod
    def load_plugins(cls):
        """
        Dynamically imports all plugins found in the plugin directory.
        Gracefully catches ImportErrors or SyntaxErrors so a bad plugin
        does not crash the main application.
        """
        cls.create_plugin_directory()
        plugin_files = cls.get_plugin_files()
        
        if not plugin_files:
            log.debug("No third-party plugins found.")
            return

        log.info(f"Discovered {len(plugin_files)} plugin(s). Attempting to load...")

        # Add the plugin directory to sys.path so plugins can potentially
        # import local helper files if they need to, although top-level is preferred.
        plugin_str_path = str(PLUGIN_DIR)
        if plugin_str_path not in sys.path:
            sys.path.insert(0, plugin_str_path)

        for p_file in plugin_files:
            module_name = f"synaptipy_plugin_{p_file.stem}"
            try:
                # Use standard importlib to dynamically load the module from file path
                spec = importlib.util.spec_from_file_location(module_name, str(p_file))
                if spec is None or spec.loader is None:
                    log.warning(f"Could not load plugin specification for {p_file.name}")
                    continue
                    
                module = importlib.util.module_from_spec(spec)
                
                # We need to manually add the module to sys.modules
                sys.modules[module_name] = module
                
                # Execute the module (This triggers the @AnalysisRegistry.register decorators!)
                spec.loader.exec_module(module)
                
                log.info(f"Successfully loaded plugin: {p_file.name}")
                
            except ImportError as e:
                log.error(f"ImportError while loading plugin '{p_file.name}': {e}", exc_info=False)
            except SyntaxError as e:
                log.error(f"SyntaxError in plugin '{p_file.name}': {e}", exc_info=False)
            except Exception as e:
                log.error(f"Unexpected error loading plugin '{p_file.name}': {e}", exc_info=False)
                
        log.info("Finished loading plugins.")

