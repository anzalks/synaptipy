# src/Synaptipy/core/analysis/registry.py
# -*- coding: utf-8 -*-
"""
Analysis Registry for dynamic function registration and lookup.

This module provides a registry pattern that allows analysis functions
to register themselves via decorators, enabling flexible pipeline configuration.
"""
import logging
from typing import Dict, Callable, Any, Optional

log = logging.getLogger(__name__)


class AnalysisRegistry:
    """
    Registry for analysis functions.

    Functions can be registered using the @AnalysisRegistry.register decorator,
    and then retrieved by name for use in batch processing pipelines.
    """

    _registry: Dict[str, Callable] = {}
    _metadata: Dict[str, Dict[str, Any]] = {}

    @classmethod
    def register(cls, name: str, type: str = "analysis", **kwargs) -> Callable:
        """
        Decorator to register an analysis or preprocessing function.

        Args:
            name: Unique identifier for the function (e.g., "spike_detection")
            type: The type of function ("analysis" or "preprocessing")
            **kwargs: Additional metadata to store with the function (e.g., ui_params)

        Returns:
            Decorator function

        Example:
            @AnalysisRegistry.register("spike_detection", ui_params=[...])
            def run_spike_detection(data, time, sampling_rate, **kwargs):
                # ... analysis logic ...
                return results_dict
        """

        def decorator(func: Callable) -> Callable:
            if name in cls._registry:
                log.warning(f"Analysis function '{name}' is already registered. Overwriting.")
            cls._registry[name] = func
            # Ensure type is stored in metadata
            meta = kwargs.copy()
            meta["type"] = type
            cls._metadata[name] = meta
            log.debug(f"Registered {type} function: {name} with metadata: {list(meta.keys())}")
            return func

        return decorator

    @classmethod
    def register_processor(cls, name: str, **kwargs) -> Callable:
        """
        Decorator to register a preprocessing function.
        Alias for register(name, type="preprocessing", **kwargs).
        """
        return cls.register(name, type="preprocessing", **kwargs)

    @classmethod
    def get_function(cls, name: str) -> Optional[Callable]:
        """
        Retrieve a registered analysis function by name.

        Args:
            name: The registered name of the function

        Returns:
            The registered function, or None if not found
        """
        func = cls._registry.get(name)
        if func is None:
            log.warning(f"Analysis function '{name}' not found in registry. Available: {list(cls._registry.keys())}")
        return func

    @classmethod
    def get_metadata(cls, name: str) -> Dict[str, Any]:
        """
        Retrieve metadata for a registered analysis function.

        Args:
            name: The registered name of the function

        Returns:
            Dictionary of metadata, or empty dict if not found
        """
        return cls._metadata.get(name, {})

    @classmethod
    def list_registered(cls) -> list:
        """
        Get a list of all registered analysis function names.

        Returns:
            List of registered function names
        """
        return list(cls._registry.keys())

    @classmethod
    def list_by_type(cls, type_str: str) -> list:
        """
        Get registered function names filtered by type.

        Args:
            type_str: The type to filter by (e.g., "analysis", "preprocessing")

        Returns:
            List of function names matching the given type
        """
        return [
            name for name, meta in cls._metadata.items()
            if meta.get("type") == type_str
        ]

    @classmethod
    def list_preprocessing(cls) -> list:
        """Get all registered preprocessing function names."""
        return cls.list_by_type("preprocessing")

    @classmethod
    def list_analysis(cls) -> list:
        """Get all registered analysis function names (excludes preprocessing)."""
        return [
            name for name, meta in cls._metadata.items()
            if meta.get("type", "analysis") == "analysis"
        ]

    @classmethod
    def clear(cls):
        """
        Clear all registered functions (mainly for testing).
        """
        cls._registry.clear()
        cls._metadata.clear()
        log.debug("Analysis registry cleared")
