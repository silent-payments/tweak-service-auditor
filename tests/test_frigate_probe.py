import asyncio
import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from frigate_probe import (
    G, N, P,
    CandidateTx,
    compress_pubkey,
    decompress_pubkey,
    derive_canary_keys,
    point_add,
    point_mul,
    point_neg,
    tagged_hash,
    FrigateProbeClient,
)


class TestFrigateProbeMath(unittest.TestCase):
    """Test pure-Python secp256k1 and BIP 352 math in frigate_probe"""

    def test_curve_generator_point(self):
        """Verify generator point G multiplied by 1 is G"""
        self.assertEqual(point_mul(G, 1), G)

    def test_point_negation_and_addition(self):
        """Verify P + (-P) = None (infinity)"""
        neg_G = point_neg(G)
        self.assertIsNotNone(neg_G)
        self.assertIsNone(point_add(G, neg_G))

    def test_pubkey_compression_roundtrip(self):
        """Verify compressing and decompressing pubkeys preserves point"""
        pt = point_mul(G, 42)
        comp = compress_pubkey(pt)
        self.assertEqual(len(comp), 33)
        decomp = decompress_pubkey(comp)
        self.assertEqual(decomp, pt)

    def test_x_only_pubkey_decompression(self):
        """Verify 32-byte x-only pubkey assumes even y"""
        pt = point_mul(G, 1337)
        if pt[1] % 2 != 0:
            pt = point_neg(pt)
        x_only = pt[0].to_bytes(32, "big")
        decomp = decompress_pubkey(x_only)
        self.assertEqual(decomp, pt)

    def test_canary_reverse_derivation_algebraic_invariance(self):
        """
        Verify that for arbitrary A_sum and P_target:
        B_spend + t_0 * G == P_target
        """
        # Choose arbitrary private keys to generate test points
        a_priv = 987654321
        p_priv = 123456789
        b_scan = 55555

        A_sum = point_mul(G, a_priv)
        P_target = point_mul(G, p_priv)
        if P_target[1] % 2 != 0:
            P_target = point_neg(P_target)

        tweak_hex = compress_pubkey(A_sum).hex()
        output_hex = compress_pubkey(P_target).hex()

        scan_priv_hex, spend_pub_hex, target_hex = derive_canary_keys(
            tweak_hex, output_hex, b_scan_scalar=b_scan
        )

        # Now simulate Frigate's exact internal derivation
        B_spend = decompress_pubkey(bytes.fromhex(spend_pub_hex))
        S = point_mul(A_sum, b_scan)
        S_bytes = compress_pubkey(S)
        t0_bytes = tagged_hash("BIP0352/SharedSecret", S_bytes + (0).to_bytes(4, "big"))
        t0 = int.from_bytes(t0_bytes, "big") % N
        T0 = point_mul(G, t0)

        frigate_derived_output = point_add(B_spend, T0)
        self.assertEqual(frigate_derived_output, P_target)
        self.assertEqual(compress_pubkey(frigate_derived_output).hex(), target_hex)


class TestFrigateProbeClientMock(unittest.TestCase):
    """Test FrigateProbeClient network communication and batch parsing with mocks"""

    @patch("asyncio.open_connection")
    def test_probe_tweak_match(self, mock_open_conn):
        mock_reader = AsyncMock()
        mock_writer = MagicMock()
        mock_writer.drain = AsyncMock()
        mock_writer.wait_closed = AsyncMock()
        mock_open_conn.return_value = (mock_reader, mock_writer)

        # Feed simulated lines from Frigate:
        # 1. Handshake response
        # 2. Subscription response with address
        # 3. Notification with history (match) and progress 1.0
        # 4. Unsubscribe response (not read)
        mock_reader.readline.side_effect = [
            b'{"id": 1, "result": ["Frigate 1.5.3", "1.4"], "jsonrpc": "2.0"}\n',
            b'{"id": 2, "result": {"address": "sp1qqmockaddress", "labels": [0], "start_height": 200000}, "jsonrpc": "2.0"}\n',
            b'{"jsonrpc": "2.0", "method": "blockchain.silentpayments.subscribe", "params": {"subscription": {"address": "sp1qqmockaddress"}, "progress": 1.0, "history": [{"tx_hash": "tx123", "height": 200000}]}}\n',
        ]

        client = FrigateProbeClient("127.0.0.1", 57001)
        tweak_hex = compress_pubkey(point_mul(G, 10)).hex()
        output_hex = compress_pubkey(point_mul(G, 20)).hex()

        result = asyncio.run(client.probe_tweak(200000, tweak_hex, output_hex, b_scan_scalar=7))

        self.assertTrue(result.success)
        self.assertTrue(result.matched)
        self.assertEqual(len(result.discovered_history), 1)
        self.assertEqual(result.discovered_history[0]["tx_hash"], "tx123")
        self.assertEqual(result.subscribed_address, "sp1qqmockaddress")

    @patch("asyncio.open_connection")
    def test_probe_batch_multiple_candidates(self, mock_open_conn):
        mock_reader = AsyncMock()
        mock_writer = MagicMock()
        mock_writer.drain = AsyncMock()
        mock_writer.wait_closed = AsyncMock()
        mock_open_conn.return_value = (mock_reader, mock_writer)

        # Test batch of 2 candidates: one matches, one does not match
        candidates = [
            CandidateTx(index=0, txid="txA", tweak_hex=compress_pubkey(point_mul(G, 11)).hex(),
                        output_pubkey_hex=compress_pubkey(point_mul(G, 21)).hex()),
            CandidateTx(index=1, txid="txB", tweak_hex=compress_pubkey(point_mul(G, 12)).hex(),
                        output_pubkey_hex=compress_pubkey(point_mul(G, 22)).hex())
        ]

        mock_reader.readline.side_effect = [
            # Handshake
            b'{"id": 1, "result": ["Frigate 1.5.3", "1.4"], "jsonrpc": "2.0"}\n',
            # Sub 1 response
            b'{"id": 2, "result": {"address": "sp1addr_A", "labels": [0]}, "jsonrpc": "2.0"}\n',
            # Sub 2 response
            b'{"id": 3, "result": {"address": "sp1addr_B", "labels": [0]}, "jsonrpc": "2.0"}\n',
            # Notification for A with hit
            b'{"jsonrpc": "2.0", "method": "blockchain.silentpayments.subscribe", "params": {"subscription": {"address": "sp1addr_A"}, "progress": 1.0, "history": [{"tx_hash": "txA"}]}}\n',
            # Notification for B with no hit
            b'{"jsonrpc": "2.0", "method": "blockchain.silentpayments.subscribe", "params": {"subscription": {"address": "sp1addr_B"}, "progress": 1.0, "history": []}}\n',
        ]

        client = FrigateProbeClient("127.0.0.1", 57001)
        results = asyncio.run(client.probe_batch(850000, candidates, b_scan_scalars=[101, 102]))

        self.assertEqual(len(results), 2)
        # First candidate matched
        self.assertTrue(results[0].matched)
        self.assertEqual(results[0].candidate_index, 0)
        self.assertEqual(results[0].target_txid, "txA")
        # Second candidate mismatched (0 hits)
        self.assertFalse(results[1].matched)
        self.assertEqual(results[1].candidate_index, 1)
        self.assertEqual(results[1].target_txid, "txB")


class TestFrigateProbeEndpoint(unittest.TestCase):
    """Live integration test against FRIGATE_ENDPOINT when configured"""

    def setUp(self):
        self.endpoint = os.getenv("FRIGATE_ENDPOINT")
        if not self.endpoint:
            self.skipTest("FRIGATE_ENDPOINT not configured")

    def test_live_probe_connection(self):
        host, port = self.endpoint.split(":")
        client = FrigateProbeClient(host, int(port))

        tweak_hex = compress_pubkey(point_mul(G, 100)).hex()
        output_hex = compress_pubkey(point_mul(G, 200)).hex()

        # Probe with random tweak/output should connect and return 0 matches cleanly
        result = asyncio.run(client.probe_tweak(968270, tweak_hex, output_hex))
        self.assertTrue(result.success, f"Probe failed: {result.error_message}")
        self.assertFalse(result.matched)
        self.assertEqual(result.discovered_history, [])
        self.assertTrue(result.subscribed_address.startswith("sp1"))


if __name__ == "__main__":
    unittest.main()
