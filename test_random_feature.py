#!/usr/bin/env python3
"""
Test script to verify the random message feature implementation.
"""

import sys
import os
sys.path.insert(0, os.path.abspath('.'))

from tgcf.config import Config, LiveSettings, read_config, write_config
from tgcf.random_handler import reset_daily_counters
import json

def test_config_structure():
    """Test that the configuration structure includes random settings."""
    config = Config()
    
    # Test default values
    assert hasattr(config.live, 'random_enabled'), "random_enabled field missing"
    assert hasattr(config.live, 'random_delay'), "random_delay field missing"
    assert hasattr(config.live, 'random_count'), "random_count field missing"
    assert hasattr(config.live, 'random_total_limit'), "random_total_limit field missing"
    assert hasattr(config.live, 'random_active_sources'), "random_active_sources field missing"
    
    # Test default values
    assert config.live.random_enabled == False, "Default random_enabled should be False"
    assert config.live.random_delay == 300, "Default random_delay should be 300"
    assert config.live.random_count == 5, "Default random_count should be 5"
    assert config.live.random_total_limit == 0, "Default random_total_limit should be 0"
    assert config.live.random_active_sources == [], "Default random_active_sources should be empty list"
    
    print("✅ Configuration structure test passed!")

def test_config_serialization():
    """Test that the configuration can be serialized and deserialized."""
    config = Config()
    
    # Modify random settings
    config.live.random_enabled = True
    config.live.random_delay = 600
    config.live.random_count = 10
    config.live.random_total_limit = 100
    config.live.random_active_sources = ["123456", "-987654"]
    
    # Convert to dict and back
    config_dict = config.dict()
    new_config = Config(**config_dict)
    
    # Verify values
    assert new_config.live.random_enabled == True
    assert new_config.live.random_delay == 600
    assert new_config.live.random_count == 10
    assert new_config.live.random_total_limit == 100
    assert new_config.live.random_active_sources == ["123456", "-987654"]
    
    print("✅ Configuration serialization test passed!")

def test_json_serialization():
    """Test JSON serialization (MongoDB storage compatibility)."""
    config = Config()
    config.live.random_enabled = True
    config.live.random_delay = 1800
    config.live.random_count = 3
    config.live.random_total_limit = 50
    config.live.random_active_sources = ["test_source"]
    
    # Convert to JSON and back
    json_str = config.json()
    config_data = json.loads(json_str)
    new_config = Config(**config_data)
    
    # Verify values
    assert new_config.live.random_enabled == True
    assert new_config.live.random_delay == 1800
    assert new_config.live.random_count == 3
    assert new_config.live.random_total_limit == 50
    assert new_config.live.random_active_sources == ["test_source"]
    
    print("✅ JSON serialization test passed!")

def test_random_handler_functions():
    """Test random handler utility functions."""
    # Test reset function
    from tgcf import storage as st
    
    # Add some fake data
    st.random_message_count[123] = 10
    st.random_message_count[456] = 20
    
    # Reset counters
    reset_daily_counters()
    
    # Verify reset
    assert len(st.random_message_count) == 0, "Counters should be reset"
    
    print("✅ Random handler functions test passed!")

def print_feature_overview():
    """Print an overview of the random message feature."""
    print("\n" + "="*60)
    print("🎲 RANDOM MESSAGE FEATURE OVERVIEW")
    print("="*60)
    print("✅ Feature Components:")
    print("   • Configuration fields added to LiveSettings")
    print("   • RandomMessageHandler class for async posting")
    print("   • Integration with live.py for parallel operation")
    print("   • Web UI controls in Advanced settings page")
    print("   • Automatic MongoDB/JSON storage support")
    print("   • Daily counters and message history tracking")
    print()
    print("🎯 Key Features:")
    print("   • Works parallel to normal live forwarding")
    print("   • Independent from 'Forwards per day' limit")
    print("   • Configurable delay between message batches")
    print("   • Configurable number of messages per batch")
    print("   • Daily total limit per source (optional)")
    print("   • Source-specific activation")
    print("   • Automatic message deduplication")
    print("   • Plugin support (filters, watermarks, etc.)")
    print("   • Visual indicator for random messages")
    print()
    print("⚙️ Configuration Options:")
    config = Config()
    print(f"   • random_enabled: {config.live.random_enabled} (Enable/disable feature)")
    print(f"   • random_delay: {config.live.random_delay}s (Delay between batches)")
    print(f"   • random_count: {config.live.random_count} (Messages per batch)")
    print(f"   • random_total_limit: {config.live.random_total_limit} (Daily limit per source)")
    print(f"   • random_active_sources: {config.live.random_active_sources} (Active source IDs)")
    print()
    print("💾 Storage:")
    print("   • All settings automatically stored in MongoDB/JSON")
    print("   • Real-time updates through web UI")
    print("   • Persistent message history and counters")
    print("="*60)

if __name__ == "__main__":
    print("🧪 Testing Random Message Feature Implementation")
    print("-" * 50)
    
    try:
        test_config_structure()
        test_config_serialization()
        test_json_serialization()
        test_random_handler_functions()
        
        print("\n🎉 All tests passed successfully!")
        print_feature_overview()
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        sys.exit(1)
