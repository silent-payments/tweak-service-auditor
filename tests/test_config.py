"""
Unit tests for ConfigManager and 3-tier configuration hierarchy.
"""
import unittest
from unittest.mock import patch
import os
import tempfile
import json
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from config import ConfigManager, expand_env_vars
from models import ServiceType


class TestConfigManager(unittest.TestCase):
    """Test 3-tier configuration hierarchy in ConfigManager"""

    def test_expand_env_vars(self):
        """Test expansion of ${VAR:-default} and $VAR"""
        with patch.dict(os.environ, {"MY_HOST": "10.0.0.1"}, clear=False):
            # Explicit default when env var unset
            self.assertEqual(expand_env_vars("${UNSET_VAR:-127.0.0.1:51001}"), "127.0.0.1:51001")
            # Present variable expands over default
            self.assertEqual(expand_env_vars("${MY_HOST:-127.0.0.1}:5000"), "10.0.0.1:5000")
            # Simple syntax
            self.assertEqual(expand_env_vars("$MY_HOST:8080"), "10.0.0.1:8080")

    def test_tier1_dynamic_override(self):
        """Test Tier 1: Environment variable directly overrides endpoint in JSON"""
        config_data = {
            "services": [
                {
                    "name": "rbitcoin",
                    "service_type": "socket_rpc",
                    "endpoint": "127.0.0.1:51001",
                    "active": False
                }
            ],
            "service_pairs": []
        }
        with tempfile.NamedTemporaryFile("w+", suffix=".json", delete=False) as tf:
            json.dump(config_data, tf)
            tf_path = tf.name

        try:
            with patch.dict(os.environ, {"RBITCOIN_ENDPOINT": "192.168.86.44:51001"}):
                cfg = ConfigManager(tf_path)
                self.assertEqual(len(cfg.services), 1)
                self.assertEqual(cfg.services[0].endpoint, "192.168.86.44:51001")
                # When overridden by environment variable, service is activated
                self.assertTrue(cfg.services[0].active)
        finally:
            if os.path.exists(tf_path):
                os.remove(tf_path)

    def test_tier2_json_expansion(self):
        """Test Tier 2: Expanding ${VAR:-default} in JSON config files"""
        config_data = {
            "services": [
                {
                    "name": "custom-service",
                    "service_type": "http",
                    "endpoint": "${CUSTOM_ENDPOINT:-http://default.local:8000}",
                    "active": True
                }
            ],
            "service_pairs": []
        }
        with tempfile.NamedTemporaryFile("w+", suffix=".json", delete=False) as tf:
            json.dump(config_data, tf)
            tf_path = tf.name

        try:
            # When CUSTOM_ENDPOINT is unset, uses default
            cfg = ConfigManager(tf_path)
            self.assertEqual(cfg.services[0].endpoint, "http://default.local:8000")

            # When CUSTOM_ENDPOINT is set, expands it
            with patch.dict(os.environ, {"CUSTOM_ENDPOINT": "https://live.api.org"}):
                cfg2 = ConfigManager(tf_path)
                self.assertEqual(cfg2.services[0].endpoint, "https://live.api.org")
        finally:
            if os.path.exists(tf_path):
                os.remove(tf_path)

    def test_tier3_pure_environment_discovery(self):
        """Test Tier 3: Zero-config auto-discovery when no config file exists"""
        non_existent_file = "/tmp/non_existent_config_12345.json"

        env = {
            "RBITCOIN_ENDPOINT": "192.168.86.44:51001",
            "BLINDBIT_GRPC_ENDPOINT": "192.168.86.44:51051"
        }
        with patch.dict(os.environ, env, clear=True):
            cfg = ConfigManager(non_existent_file)
            self.assertEqual(len(cfg.services), 2)
            service_names = {s.name for s in cfg.services}
            self.assertEqual(service_names, {"rbitcoin", "blindbit-grpc"})

            # Auto-pairing
            self.assertEqual(len(cfg.service_pairs), 1)
            pair = cfg.service_pairs[0]
            self.assertEqual(pair.name, "rbitcoin-vs-blindbit-grpc")
            self.assertTrue(pair.active)

            # Validates with 0 issues
            self.assertEqual(cfg.validate_config(), [])


if __name__ == '__main__':
    unittest.main()
