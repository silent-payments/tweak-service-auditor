"""
Unit and endpoint tests for RBitcoinService.
Tests that connect to a running service execute when RBITCOIN_ENDPOINT is configured.
"""
import unittest
from unittest.mock import Mock, patch, AsyncMock
import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from models import ServiceConfig, ServiceType
from service_implementations import RBitcoinService, create_service_instance


class TestRBitcoinService(unittest.TestCase):
    """Unit tests for RBitcoinService with mocks"""

    def setUp(self):
        self.config = ServiceConfig(
            name="rbitcoin-signet",
            service_type=ServiceType.SOCKET_RPC,
            endpoint="127.0.0.1:50001",
            timeout=10,
            active=True
        )
        self.service = RBitcoinService(self.config)

    def test_factory_instantiation(self):
        """Test create_service_instance returns RBitcoinService for rbitcoin names"""
        service = create_service_instance(self.config)
        self.assertIsInstance(service, RBitcoinService)
        self.assertEqual(service.host, "127.0.0.1")
        self.assertEqual(service.port, 50001)

    def test_build_rpc_call(self):
        """Test _build_rpc_call constructs blockchain.tweaks.subscribe with [height, 1]"""
        method, params = self.service._build_rpc_call(200000)
        self.assertEqual(method, 'blockchain.tweaks.subscribe')
        self.assertEqual(params, [200000, 1])

    def test_normalize_response_dict(self):
        """Test normalization of standard rbitcoin response format"""
        raw = {
            "200000": {
                "aabbccddeeff": {
                    "tweak": "02" + "ab" * 32,
                    "output_pubkeys": {"0": ["02" + "cd" * 32, 10000]}
                }
            }
        }
        tweaks = self.service._normalize_response(raw, 200000)
        self.assertEqual(len(tweaks), 1)
        self.assertEqual(tweaks[0].tweak_hash, "02" + "ab" * 32)
        self.assertEqual(tweaks[0].block_height, 200000)
        self.assertEqual(tweaks[0].transaction_id, "aabbccddeeff")
        self.assertEqual(tweaks[0].output_index, 0)

    def test_normalize_response_skips_zero_and_invalid_tweaks(self):
        """Test normalization filters out non-standard or all-zero tweaks"""
        raw = {
            "200000": {
                "coinbase_tx": {
                    "tweak": "00" * 33
                },
                "short_tweak": {
                    "tweak": "02abcd"
                },
                "valid_tx": {
                    "tweak": "03" + "ff" * 32
                }
            }
        }
        tweaks = self.service._normalize_response(raw, 200000)
        self.assertEqual(len(tweaks), 1)
        self.assertEqual(tweaks[0].tweak_hash, "03" + "ff" * 32)

    def test_normalize_empty_response(self):
        """Test normalization with empty block data"""
        tweaks_empty = self.service._normalize_response({}, 200000)
        self.assertEqual(tweaks_empty, [])
        tweaks_none = self.service._normalize_response(None, 200000)
        self.assertEqual(tweaks_none, [])

    @patch('service_interface.AsyncConnection')
    def test_get_tweaks_for_block_success(self, mock_conn_cls):
        """Test get_tweaks_for_block end-to-end with mock connection"""
        async def run_test():
            mock_conn = AsyncMock()
            mock_conn.call.return_value = {
                "jsonrpc": "2.0",
                "id": 0,
                "result": {
                    "200000": {
                        "tx1": {"tweak": "03" + "11" * 32, "output_pubkeys": {}}
                    }
                }
            }
            mock_conn_cls.return_value.__aenter__.return_value = mock_conn

            res = await self.service.get_tweaks_for_block(200000)
            self.assertTrue(res.success)
            self.assertEqual(res.block_height, 200000)
            self.assertEqual(len(res.tweaks), 1)
            self.assertEqual(res.tweaks[0].tweak_hash, "03" + "11" * 32)
            mock_conn.call.assert_called_once_with('blockchain.tweaks.subscribe', 200000, 1)

        asyncio.run(run_test())


@unittest.skipUnless(os.getenv("RBITCOIN_ENDPOINT"), "RBITCOIN_ENDPOINT not configured")
class TestRBitcoinEndpoint(unittest.TestCase):
    """Endpoint tests for rbitcoin-node"""

    def setUp(self):
        self.endpoint = os.getenv("RBITCOIN_ENDPOINT")
        self.config = ServiceConfig(
            name="rbitcoin-endpoint",
            service_type=ServiceType.SOCKET_RPC,
            endpoint=self.endpoint,
            timeout=15,
            active=True
        )
        self.service = RBitcoinService(self.config)

    def test_endpoint_block_200000(self):
        """Test querying rbitcoin via RBITCOIN_ENDPOINT for Signet block 200000"""
        async def run():
            result = await self.service.get_tweaks_for_block(200000)
            self.assertTrue(result.success, f"Failed to query rbitcoin at {self.endpoint}: {result.error_message}")
            self.assertEqual(len(result.tweaks), 133, f"Expected 133 tweaks for block 200000, got {len(result.tweaks)}")
            self.assertEqual(result.block_height, 200000)

        asyncio.run(run())


if __name__ == '__main__':
    unittest.main()
