"""
Unit and endpoint tests for BlindBit gRPC service.
Tests that connect to a running service execute when BLINDBIT_GRPC_ENDPOINT is configured.
"""
import unittest
from unittest.mock import Mock, patch
import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from models import ServiceConfig, ServiceType


class TestBlindBitGRPCService(unittest.TestCase):
    """Test BlindBit gRPC service implementation with mocks"""

    def setUp(self):
        """Set up test fixtures"""
        self.config = ServiceConfig(
            name="test-blindbit-grpc",
            service_type=ServiceType.GRPC,
            endpoint="127.0.0.1:50051",
            timeout=5,
            active=True
        )

        self.config_with_dust = ServiceConfig(
            name="test-blindbit-grpc-dust",
            service_type=ServiceType.GRPC,
            endpoint="127.0.0.1:50051",
            timeout=5,
            active=True,
            dust_limit=546
        )

    @patch('grpc.insecure_channel')
    @patch('pb.oracle_service_pb2_grpc.OracleServiceStub')
    @patch('pb.indexing_server_pb2.BlockHeightRequest')
    @patch('pb.indexing_server_pb2.GetTweakIndexRequest')
    def test_service_initialization(self, mock_get_tweak_req, mock_block_req, mock_stub_class, mock_channel):
        """Test service initialization"""
        from service_implementations import BlindBitGRPCService

        service = BlindBitGRPCService(self.config)
        self.assertEqual(service.config.name, "test-blindbit-grpc")
        self.assertEqual(service.target, "127.0.0.1:50051")
        self.assertEqual(service.host, "127.0.0.1")
        self.assertEqual(service.port, 50051)

    def test_invalid_config(self):
        """Test service fails with invalid config"""
        invalid_config = ServiceConfig(
            name="test-invalid",
            service_type=ServiceType.HTTP,  # Wrong type
            endpoint="127.0.0.1:50051"
        )

        with patch('grpc.insecure_channel'), \
             patch('pb.oracle_service_pb2_grpc.OracleServiceStub'), \
             patch('pb.indexing_server_pb2.BlockHeightRequest'), \
             patch('pb.indexing_server_pb2.GetTweakIndexRequest'):

            from service_implementations import BlindBitGRPCService
            with self.assertRaises(ValueError):
                BlindBitGRPCService(invalid_config)

    @patch('grpc.insecure_channel')
    @patch('pb.oracle_service_pb2_grpc.OracleServiceStub')
    @patch('pb.indexing_server_pb2.BlockHeightRequest')
    @patch('pb.indexing_server_pb2.GetTweakIndexRequest')
    def test_endpoint_parsing(self, mock_get_tweak_req, mock_block_req, mock_stub_class, mock_channel):
        """Test various endpoint formats"""
        from service_implementations import BlindBitGRPCService

        test_cases = [
            ("127.0.0.1:50051", "127.0.0.1", 50051),
            ("grpc://localhost:9000", "localhost", 9000),
            ("blindbit.example.com:443", "blindbit.example.com", 443)
        ]

        for endpoint, expected_host, expected_port in test_cases:
            config = ServiceConfig(
                name="test",
                service_type=ServiceType.GRPC,
                endpoint=endpoint
            )

            service = BlindBitGRPCService(config)
            self.assertEqual(service.host, expected_host)
            self.assertEqual(service.port, expected_port)

    def test_get_tweaks_basic(self):
        """Test basic tweak retrieval"""
        async def run_test():
            with patch('grpc.insecure_channel') as mock_channel_func, \
                 patch('pb.oracle_service_pb2_grpc.OracleServiceStub') as mock_stub_class, \
                 patch('pb.indexing_server_pb2.BlockHeightRequest') as mock_block_req, \
                 patch('pb.indexing_server_pb2.GetTweakIndexRequest') as mock_get_tweak_req:

                mock_channel = Mock()
                mock_channel_func.return_value = mock_channel

                mock_stub = Mock()
                mock_stub_class.return_value = mock_stub

                mock_response = Mock()
                mock_response.tweaks = [b'\x01' * 33, b'\x02' * 33]
                mock_stub.GetTweakArray.return_value = mock_response

                from service_implementations import BlindBitGRPCService
                service = BlindBitGRPCService(self.config)
                result = await service.get_tweaks_for_block(12345)

                self.assertTrue(result.success)
                self.assertEqual(result.block_height, 12345)
                self.assertEqual(len(result.tweaks), 2)
                self.assertEqual(result.tweaks[0].tweak_hash, '01' * 33)
                self.assertEqual(result.tweaks[1].tweak_hash, '02' * 33)

                mock_stub.GetTweakArray.assert_called_once()

        asyncio.run(run_test())

    def test_get_tweaks_with_dust_limit(self):
        """Test tweak retrieval with dust limit"""
        async def run_test():
            with patch('grpc.insecure_channel') as mock_channel_func, \
                 patch('pb.oracle_service_pb2_grpc.OracleServiceStub') as mock_stub_class, \
                 patch('pb.indexing_server_pb2.BlockHeightRequest') as mock_block_req, \
                 patch('pb.indexing_server_pb2.GetTweakIndexRequest') as mock_get_tweak_req:

                mock_channel = Mock()
                mock_channel_func.return_value = mock_channel

                mock_stub = Mock()
                mock_stub_class.return_value = mock_stub

                mock_response = Mock()
                mock_response.tweaks = [b'\x03' * 33]
                mock_stub.GetTweakIndexArray.return_value = mock_response

                from service_implementations import BlindBitGRPCService
                service = BlindBitGRPCService(self.config_with_dust)
                result = await service.get_tweaks_for_block(12345)

                self.assertTrue(result.success)
                self.assertEqual(len(result.tweaks), 1)
                self.assertEqual(result.tweaks[0].tweak_hash, '03' * 33)

                mock_stub.GetTweakIndexArray.assert_called_once()
                mock_stub.GetTweakArray.assert_not_called()

        asyncio.run(run_test())

    def test_grpc_error_handling(self):
        """Test gRPC error handling"""
        async def run_test():
            with patch('grpc.insecure_channel') as mock_channel_func, \
                 patch('pb.oracle_service_pb2_grpc.OracleServiceStub') as mock_stub_class, \
                 patch('pb.indexing_server_pb2.BlockHeightRequest') as mock_block_req, \
                 patch('pb.indexing_server_pb2.GetTweakIndexRequest') as mock_get_tweak_req:

                mock_channel = Mock()
                mock_channel_func.return_value = mock_channel

                mock_stub = Mock()
                mock_stub_class.return_value = mock_stub
                mock_stub.GetTweakArray.side_effect = Exception("gRPC connection failed")

                from service_implementations import BlindBitGRPCService
                service = BlindBitGRPCService(self.config)
                with self.assertLogs(service.logger, level='ERROR'):
                    result = await service.get_tweaks_for_block(12345)

                self.assertFalse(result.success)
                self.assertEqual(len(result.tweaks), 0)
                self.assertIn("gRPC connection failed", result.error_message)

        asyncio.run(run_test())

    @patch('grpc.insecure_channel')
    @patch('pb.oracle_service_pb2_grpc.OracleServiceStub')
    @patch('pb.indexing_server_pb2.BlockHeightRequest')
    @patch('pb.indexing_server_pb2.GetTweakIndexRequest')
    def test_normalize_response_empty(self, mock_get_tweak_req, mock_block_req, mock_stub_class, mock_channel):
        """Test response normalization with empty data"""
        from service_implementations import BlindBitGRPCService

        service = BlindBitGRPCService(self.config)

        mock_response = Mock()
        mock_response.tweaks = []

        tweaks = service._normalize_response(mock_response, 12345)
        self.assertEqual(len(tweaks), 0)

    @patch('grpc.insecure_channel')
    @patch('pb.oracle_service_pb2_grpc.OracleServiceStub')
    @patch('pb.indexing_server_pb2.BlockHeightRequest')
    @patch('pb.indexing_server_pb2.GetTweakIndexRequest')
    def test_normalize_response_with_data(self, mock_get_tweak_req, mock_block_req, mock_stub_class, mock_channel):
        """Test response normalization with real data"""
        from service_implementations import BlindBitGRPCService

        service = BlindBitGRPCService(self.config)

        mock_response = Mock()
        mock_response.tweaks = [b'\xaa' * 33, b'\xbb' * 33]

        tweaks = service._normalize_response(mock_response, 12345)

        self.assertEqual(len(tweaks), 2)
        self.assertEqual(tweaks[0].tweak_hash, 'aa' * 33)
        self.assertEqual(tweaks[0].block_height, 12345)
        self.assertEqual(tweaks[0].output_index, 0)
        self.assertEqual(tweaks[0].raw_data['source'], 'blindbit_grpc_oracle')

        self.assertEqual(tweaks[1].tweak_hash, 'bb' * 33)
        self.assertEqual(tweaks[1].block_height, 12345)
        self.assertEqual(tweaks[1].output_index, 1)


@unittest.skipUnless(os.getenv("BLINDBIT_GRPC_ENDPOINT"), "BLINDBIT_GRPC_ENDPOINT not configured")
class TestBlindBitGRPCEndpoint(unittest.TestCase):
    """Endpoint tests for BlindBit gRPC service"""

    def setUp(self):
        self.endpoint = os.getenv("BLINDBIT_GRPC_ENDPOINT")
        self.config = ServiceConfig(
            name="blindbit-grpc-endpoint",
            service_type=ServiceType.GRPC,
            endpoint=self.endpoint,
            timeout=15,
            active=True
        )
        from service_implementations import BlindBitGRPCService
        self.service = BlindBitGRPCService(self.config)

    def test_endpoint_block_200000(self):
        """Test querying BlindBit gRPC via BLINDBIT_GRPC_ENDPOINT for Signet block 200000"""
        async def run():
            result = await self.service.get_tweaks_for_block(200000)
            self.assertTrue(result.success, f"Failed to query BlindBit gRPC at {self.endpoint}: {result.error_message}")
            self.assertEqual(len(result.tweaks), 133, f"Expected 133 tweaks for block 200000, got {len(result.tweaks)}")
            self.assertEqual(result.block_height, 200000)

        asyncio.run(run())


if __name__ == '__main__':
    unittest.main()
