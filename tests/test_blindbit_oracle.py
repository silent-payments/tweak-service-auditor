"""
Unit and endpoint tests for BlindBit Oracle HTTP service.
Tests that connect to a running service execute when BLINDBIT_HTTP_ENDPOINT is configured.
"""
import unittest
import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from models import ServiceConfig, ServiceType
from service_implementations import TweakIndexHTTPService, create_service_instance


class TestBlindBitOracleURL(unittest.TestCase):
    """Unit tests for BlindBit Oracle HTTP URL construction"""

    def setUp(self):
        self.config = ServiceConfig(
            name="blindbit-oracle",
            service_type=ServiceType.HTTP,
            endpoint="http://127.0.0.1:8000/tweak-index",
            headers={"User-Agent": "TweakServiceAuditor/1.0"},
            timeout=30
        )
        self.service = create_service_instance(self.config)

    def test_url_construction(self):
        """Test URL construction for different block heights"""
        test_heights = [258257, 800000, 1000000]
        for height in test_heights:
            url = self.service._build_url(height)
            expected = f"http://127.0.0.1:8000/tweak-index/{height}"
            self.assertEqual(url, expected)


@unittest.skipUnless(os.getenv("BLINDBIT_HTTP_ENDPOINT"), "BLINDBIT_HTTP_ENDPOINT not configured")
class TestBlindBitOracleEndpoint(unittest.TestCase):
    """Endpoint tests for BlindBit Oracle HTTP service"""

    def setUp(self):
        self.endpoint = os.getenv("BLINDBIT_HTTP_ENDPOINT")
        self.config = ServiceConfig(
            name="blindbit-oracle-endpoint",
            service_type=ServiceType.HTTP,
            endpoint=self.endpoint,
            headers={"User-Agent": "TweakServiceAuditor/1.0"},
            timeout=15,
            active=True
        )
        self.service = create_service_instance(self.config)

    def test_endpoint_block_258257(self):
        """Test querying BlindBit HTTP Oracle via BLINDBIT_HTTP_ENDPOINT for block 258257"""
        async def run():
            result = await self.service.get_tweaks_for_block(258257)
            self.assertTrue(result.success, f"Failed to query BlindBit HTTP at {self.endpoint}: {result.error_message}")
            self.assertGreater(len(result.tweaks), 0)

        asyncio.run(run())


if __name__ == '__main__':
    unittest.main()
