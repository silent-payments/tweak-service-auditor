"""
Endpoint tests for Esplora Cake socket RPC service.
Tests execute when ESPLORA_ENDPOINT is configured.
"""
import unittest
import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from models import ServiceConfig, ServiceType
from service_implementations import ElectrsRPCService


@unittest.skipUnless(os.getenv("ESPLORA_ENDPOINT"), "ESPLORA_ENDPOINT not configured")
class TestEsploraCakeEndpoint(unittest.TestCase):
    """Endpoint tests for Esplora Cake / Electrs socket RPC"""

    def setUp(self):
        self.endpoint = os.getenv("ESPLORA_ENDPOINT")
        self.config = ServiceConfig(
            name="esplora-cake-endpoint",
            service_type=ServiceType.SOCKET_RPC,
            endpoint=self.endpoint,
            timeout=15,
            active=True
        )
        self.service = ElectrsRPCService(self.config)

    def test_endpoint_block_258257(self):
        """Test querying Esplora Cake via ESPLORA_ENDPOINT for block 258257"""
        async def run():
            result = await self.service.get_tweaks_for_block(258257)
            self.assertTrue(result.success, f"Failed to query Esplora Cake at {self.endpoint}: {result.error_message}")
            self.assertGreater(len(result.tweaks), 0)

        asyncio.run(run())


if __name__ == '__main__':
    unittest.main()
