# src/Synaptipy/core/analysis/registry.py
# -*- coding: utf-8 -*-
"""
Analysis Registry for dynamic function registration and lookup.

This module provides a registry pattern that allows analysis functions
to register themselves via decorators, enabling flexible pipeline configuration.
"""
import logging
from typing import Dict, Callable, Any, Optional

log = logging.getLogger('Synaptipy.core.analysis.registry')


class AnalysisRegistry:
    """
    Registry for analysis functions.
    
    Functions can be registered using the @AnalysisRegistry.register decorator,
    and then retrieved by name for use in batch processing pipelines.
    """
    
    _registry: Dict[str, Callable] = {}
    
    @classmethod
    def register(cls, name: str) -> Callable:
        """
        Decorator to register an analysis function.
        
        Args:
            name: Unique identifier for the analysis function (e.g., "spike_detection")
            
        Returns:
            Decorator function
            
        Example:
            @AnalysisRegistry.register("spike_detection")
            def run_spike_detection(data, time, sampling_rate, **kwargs):
                # ... analysis logic ...
                return results_dict
        """
        def decorator(func: Callable) -> Callable:
            if name in cls._registry:
                log.warning(f"Analysis function '{name}' is already registered. Overwriting.")
            cls._registry[name] = func
            log.debug(f"Registered analysis function: {name}")
            return func
        return decorator
    
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
    def list_registered(cls) -> list:
        """
        Get a list of all registered analysis function names.
        
        Returns:
            List of registered function names
        """
        return list(cls._registry.keys())
    
    @classmethod
    def clear(cls):
        """
        Clear all registered functions (mainly for testing).
        """
        cls._registry.clear()
        log.debug("Analysis registry cleared")


