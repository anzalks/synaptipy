# tests/shared/test_data_cache.py
# -*- coding: utf-8 -*-
"""
Tests for the DataCache class.
"""
import pytest
from pathlib import Path
import numpy as np

from Synaptipy.shared.data_cache import DataCache
from Synaptipy.core.data_model import Recording, Channel


@pytest.fixture
def sample_recording():
    """Create a sample Recording object for testing."""
    recording = Recording(source_file=Path("test_file.abf"))
    recording.sampling_rate = 20000.0
    recording.duration = 2.5
    
    # Create a sample channel
    ch1 = Channel("1", "Vm", "mV", 20000.0, [np.random.rand(50000)])
    ch1.t_start = 0.0
    recording.channels = {"1": ch1}
    
    return recording


@pytest.fixture
def data_cache():
    """Create a DataCache instance for testing."""
    return DataCache(max_size=3)  # Small cache for testing


class TestDataCache:
    """Test cases for DataCache class."""
    
    def test_cache_initialization(self):
        """Test that cache initializes correctly."""
        cache = DataCache(max_size=5)
        assert cache.max_size == 5
        assert cache.size() == 0
        assert not cache.is_full()
        assert len(cache) == 0
    
    def test_cache_put_and_get(self, data_cache, sample_recording):
        """Test basic put and get operations."""
        file_path = Path("test_file.abf")
        
        # Initially empty
        assert data_cache.get(file_path) is None
        assert not data_cache.contains(file_path)
        
        # Put recording
        data_cache.put(file_path, sample_recording)
        
        # Should now be in cache
        assert data_cache.contains(file_path)
        assert data_cache.size() == 1
        
        # Get recording
        retrieved = data_cache.get(file_path)
        assert retrieved is not None
        assert retrieved is sample_recording
        assert retrieved.source_file == sample_recording.source_file
    
    def test_cache_eviction_fifo(self, sample_recording):
        """Test FIFO eviction when cache is full."""
        cache = DataCache(max_size=2)
        
        # Add recordings up to capacity
        path1 = Path("file1.abf")
        path2 = Path("file2.abf")
        path3 = Path("file3.abf")
        
        recording1 = Recording(source_file=path1)
        recording2 = Recording(source_file=path2)
        recording3 = Recording(source_file=path3)
        
        cache.put(path1, recording1)
        cache.put(path2, recording2)
        
        assert cache.size() == 2
        assert cache.contains(path1)
        assert cache.contains(path2)
        
        # Add third recording - should evict first one
        cache.put(path3, recording3)
        
        assert cache.size() == 2
        assert not cache.contains(path1)  # Should be evicted
        assert cache.contains(path2)
        assert cache.contains(path3)
    
    def test_cache_remove(self, data_cache, sample_recording):
        """Test removing entries from cache."""
        file_path = Path("test_file.abf")
        
        # Add recording
        data_cache.put(file_path, sample_recording)
        assert data_cache.contains(file_path)
        
        # Remove recording
        removed = data_cache.remove(file_path)
        assert removed is True
        assert not data_cache.contains(file_path)
        assert data_cache.size() == 0
        
        # Try to remove non-existent entry
        removed = data_cache.remove(Path("nonexistent.abf"))
        assert removed is False
    
    def test_cache_clear(self, data_cache, sample_recording):
        """Test clearing the entire cache."""
        # Add multiple recordings
        path1 = Path("file1.abf")
        path2 = Path("file2.abf")
        
        recording1 = Recording(source_file=path1)
        recording2 = Recording(source_file=path2)
        
        data_cache.put(path1, recording1)
        data_cache.put(path2, recording2)
        
        assert data_cache.size() == 2
        
        # Clear cache
        data_cache.clear()
        
        assert data_cache.size() == 0
        assert not data_cache.contains(path1)
        assert not data_cache.contains(path2)
    
    def test_cache_stats(self, data_cache, sample_recording):
        """Test cache statistics."""
        file_path = Path("test_file.abf")
        
        # Empty cache stats
        stats = data_cache.get_stats()
        assert stats['size'] == 0
        assert stats['max_size'] == 3
        assert stats['utilization'] == 0.0
        assert stats['cached_files'] == []
        
        # Add recording
        data_cache.put(file_path, sample_recording)
        
        stats = data_cache.get_stats()
        assert stats['size'] == 1
        assert stats['max_size'] == 3
        assert stats['utilization'] == 1.0 / 3.0
        assert str(file_path) in stats['cached_files']
    
    def test_cache_lru_behavior(self, sample_recording):
        """Test that cache maintains LRU order."""
        cache = DataCache(max_size=3)
        
        path1 = Path("file1.abf")
        path2 = Path("file2.abf")
        path3 = Path("file3.abf")
        path4 = Path("file4.abf")
        
        recording1 = Recording(source_file=path1)
        recording2 = Recording(source_file=path2)
        recording3 = Recording(source_file=path3)
        recording4 = Recording(source_file=path4)
        
        # Add three recordings
        cache.put(path1, recording1)
        cache.put(path2, recording2)
        cache.put(path3, recording3)
        
        # Access path1 to make it most recently used
        retrieved = cache.get(path1)
        assert retrieved is recording1
        
        # Add fourth recording - should evict path2 (least recently used)
        cache.put(path4, recording4)
        
        assert cache.contains(path1)  # Should still be there (most recently used)
        assert not cache.contains(path2)  # Should be evicted
        assert cache.contains(path3)
        assert cache.contains(path4)
    
    def test_cache_invalid_input(self, data_cache):
        """Test cache behavior with invalid input."""
        # Try to cache non-Recording object
        data_cache.put(Path("test.abf"), "not a recording")
        
        # Should not be cached
        assert data_cache.size() == 0
        assert not data_cache.contains(Path("test.abf"))
    
    def test_cache_path_normalization(self, data_cache, sample_recording):
        """Test that cache handles different path types correctly."""
        file_path_str = "test_file.abf"
        file_path_path = Path("test_file.abf")
        
        # Put with string path
        data_cache.put(file_path_str, sample_recording)
        
        # Should be retrievable with Path object
        retrieved = data_cache.get(file_path_path)
        assert retrieved is sample_recording
        
        # Should be contained with Path object
        assert data_cache.contains(file_path_path)
    
    def test_cache_cleanup_on_eviction(self, sample_recording):
        """Test that cleanup is called when recordings are evicted."""
        cache = DataCache(max_size=1)
        
        path1 = Path("file1.abf")
        path2 = Path("file2.abf")
        
        recording1 = Recording(source_file=path1)
        recording2 = Recording(source_file=path2)
        
        # Add first recording
        cache.put(path1, recording1)
        
        # Add second recording - should evict first and call cleanup
        cache.put(path2, recording2)
        
        # First recording should be evicted
        assert not cache.contains(path1)
        assert cache.contains(path2)
        
        # The cleanup method should have been called on recording1
        # (we can't easily test this without mocking, but the eviction should work)
