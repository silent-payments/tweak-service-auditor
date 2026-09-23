#!/usr/bin/env python3
"""
Frigate Silent Payments Probe Prototype

Audits Frigate (Sparrow Wallet's BIP 352 Electrum server) without needing raw tweak endpoints
by using reverse-derived canary scan keys on arbitrary blocks and transactions.

Mathematical Principle (Method A: Reverse-Derivation Probe):
1. In BIP 352, given an input public key aggregation A_sum and output P:
      P = B_spend + hash_BIP0352/SharedSecret(b_scan * A_sum || 0) * G
2. For an arbitrary transaction with tweak A_sum and output P:
   - Pick a known random scalar b_scan (probe scan private key).
   - Compute shared secret S = b_scan * A_sum.
   - Compute tweak scalar t_0 = tagged_hash("BIP0352/SharedSecret", S || ser32(0)) mod n.
   - Compute spend public key: B_spend = P - t_0 * G.
3. Subscribe to Frigate via `blockchain.silentpayments.subscribe(b_scan, B_spend, "height-height")`.
4. Verification:
   - If Frigate correctly calculated A_sum, its internal query derives:
         B_spend + t_0 * G = (P - t_0 * G) + t_0 * G = P
     and Frigate emits a hit notification with the transaction ID!
   - If Frigate failed to index the block, calculated a different A_sum, or missed an input,
     it will derive a non-matching pubkey and report 0 hits.
"""

import argparse
import asyncio
import hashlib
import json
import logging
import os
import random
import secrets
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("frigate_probe")

# secp256k1 Curve Parameters
P = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F
N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BB5CA53629344136F
Gx = 0x79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798
Gy = 0x483ADA7726A3C4655DA4FBFC0E1108A8FD17B448A68554199C47D08FFB10D4B8
G = (Gx, Gy)


def tagged_hash(tag: str, msg: bytes) -> bytes:
    """Compute BIP 340 / BIP 352 tagged SHA256 hash."""
    tag_hash = hashlib.sha256(tag.encode("utf-8")).digest()
    return hashlib.sha256(tag_hash + tag_hash + msg).digest()


def point_add(P1: Optional[Tuple[int, int]], P2: Optional[Tuple[int, int]]) -> Optional[Tuple[int, int]]:
    """Affine point addition on secp256k1."""
    if P1 is None:
        return P2
    if P2 is None:
        return P1
    x1, y1 = P1
    x2, y2 = P2
    if x1 == x2 and y1 != y2:
        return None
    if x1 == x2:
        m = (3 * x1 * x1 * pow(2 * y1, -1, P)) % P
    else:
        m = ((y2 - y1) * pow(x2 - x1, -1, P)) % P
    x3 = (m * m - x1 - x2) % P
    y3 = (m * (x1 - x3) - y1) % P
    return (x3, y3)


def point_mul(pt: Optional[Tuple[int, int]], d: int) -> Optional[Tuple[int, int]]:
    """Scalar multiplication using double-and-add."""
    res = None
    curr = pt
    d = d % N
    while d > 0:
        if d & 1:
            res = point_add(res, curr)
        curr = point_add(curr, curr)
        d >>= 1
    return res


def point_neg(pt: Optional[Tuple[int, int]]) -> Optional[Tuple[int, int]]:
    """Negate a secp256k1 point."""
    if pt is None:
        return None
    return (pt[0], (P - pt[1]) % P)


def decompress_pubkey(b: bytes) -> Tuple[int, int]:
    """Decompress a 33-byte compressed or 32-byte x-only secp256k1 pubkey."""
    if len(b) == 32:
        # x-only Taproot pubkey -> even y
        x = int.from_bytes(b, "big")
        prefix = 2
    elif len(b) == 33:
        prefix = b[0]
        x = int.from_bytes(b[1:], "big")
    else:
        raise ValueError(f"Invalid public key length: {len(b)} bytes (expected 32 or 33)")

    y_sq = (pow(x, 3, P) + 7) % P
    y = pow(y_sq, (P + 1) // 4, P)
    if pow(y, 2, P) != y_sq:
        raise ValueError("Invalid curve point (not on secp256k1)")
    if (prefix == 2 and y % 2 != 0) or (prefix == 3 and y % 2 == 0):
        y = P - y
    return (x, y)


def compress_pubkey(pt: Tuple[int, int]) -> bytes:
    """Serialize a secp256k1 point to 33-byte compressed hex."""
    x, y = pt
    prefix = b"\x02" if y % 2 == 0 else b"\x03"
    return prefix + x.to_bytes(32, "big")


def derive_canary_keys(
    tweak_hex: str,
    output_pubkey_hex: str,
    b_scan_scalar: Optional[int] = None
) -> Tuple[str, str, str]:
    """
    Reverse-derive (scan_private_key, spend_public_key) for a target tweak and output.

    Args:
        tweak_hex: 33-byte hex of aggregated public key A_sum.
        output_pubkey_hex: 32-byte or 33-byte hex of target transaction output.
        b_scan_scalar: Optional scalar for probe scan key. If None, securely generated.

    Returns:
        (b_scan_hex, B_spend_hex, expected_target_output_hex)
    """
    A_sum = decompress_pubkey(bytes.fromhex(tweak_hex))
    P_target = decompress_pubkey(bytes.fromhex(output_pubkey_hex))

    if b_scan_scalar is None:
        b_scan_scalar = secrets.randbelow(N - 2) + 1

    b_scan_hex = b_scan_scalar.to_bytes(32, "big").hex()

    # S = b_scan * A_sum
    S = point_mul(A_sum, b_scan_scalar)
    if S is None:
        raise ValueError("Invalid shared secret (infinity point)")
    S_bytes = compress_pubkey(S)

    # t_0 = tagged_hash("BIP0352/SharedSecret", S || ser32(0))
    t0_bytes = tagged_hash("BIP0352/SharedSecret", S_bytes + (0).to_bytes(4, "big"))
    t0 = int.from_bytes(t0_bytes, "big") % N
    T0 = point_mul(G, t0)

    # B_spend = P_target - T_0
    B_spend = point_add(P_target, point_neg(T0))
    if B_spend is None:
        raise ValueError("Derived spend pubkey at infinity")
    B_spend_hex = compress_pubkey(B_spend).hex()

    return b_scan_hex, B_spend_hex, compress_pubkey(P_target).hex()


@dataclass
class CandidateTx:
    """A candidate transaction in a block with a tweak and eligible Taproot output."""
    index: int
    txid: str
    tweak_hex: str
    output_pubkey_hex: str


def fetch_candidates_from_blindbit(blindbit_endpoint: str, block_height: int) -> List[CandidateTx]:
    """
    Query BlindBit gRPC GetFullBlock to fetch all candidate transactions with tweaks and Taproot outputs.

    Returns:
        List of CandidateTx found in the block.
    """
    import grpc

    # Add pb/ to path if present
    script_dir = os.path.dirname(os.path.abspath(__file__))
    pb_dir = os.path.join(script_dir, "pb")
    if os.path.exists(pb_dir) and pb_dir not in sys.path:
        sys.path.insert(0, pb_dir)

    try:
        from pb import indexing_server_pb2, oracle_service_pb2_grpc
    except ImportError:
        import indexing_server_pb2
        import oracle_service_pb2_grpc

    channel = grpc.insecure_channel(blindbit_endpoint)
    stub = oracle_service_pb2_grpc.OracleServiceStub(channel)
    req = indexing_server_pb2.BlockHeightRequest(block_height=block_height)
    resp = stub.GetFullBlock(req, timeout=10.0)

    candidates: List[CandidateTx] = []
    for item in resp.index:
        tweak_bytes = getattr(item, "tweak", None)
        if not tweak_bytes or len(tweak_bytes) != 33:
            continue
        tweak_hex = tweak_bytes.hex()
        if tweak_hex.startswith("00"):
            continue

        utxos = getattr(item, "utxos", [])
        for u in utxos:
            pubkey_bytes = getattr(u, "pubkey", None)
            if pubkey_bytes and len(pubkey_bytes) in (32, 33):
                txid_bytes = getattr(item, "txid", b"")
                txid = txid_bytes[::-1].hex() if isinstance(txid_bytes, bytes) else str(txid_bytes)
                candidates.append(CandidateTx(
                    index=len(candidates),
                    txid=txid,
                    tweak_hex=tweak_hex,
                    output_pubkey_hex=pubkey_bytes.hex()
                ))
                break  # Pick first eligible Taproot output per transaction

    return candidates


@dataclass
class ProbeAuditResult:
    """Result of auditing a tweak against Frigate."""
    success: bool
    matched: bool
    block_height: int
    tweak_hex: str
    target_output_hex: str
    discovered_history: List[Dict[str, Any]] = field(default_factory=list)
    candidate_index: Optional[int] = None
    target_txid: Optional[str] = None
    subscribed_address: Optional[str] = None
    error_message: Optional[str] = None
    elapsed_time: float = 0.0


class FrigateProbeClient:
    """Client for probing and auditing a running Frigate Electrum instance."""

    def __init__(self, host: str, port: int, timeout: float = 15.0):
        self.host = host
        self.port = port
        self.timeout = timeout

    async def probe_tweak(
        self,
        block_height: int,
        tweak_hex: str,
        output_pubkey_hex: str,
        candidate_index: Optional[int] = None,
        target_txid: Optional[str] = None,
        b_scan_scalar: Optional[int] = None
    ) -> ProbeAuditResult:
        """Probe a single tweak against Frigate."""
        results = await self.probe_batch(
            block_height=block_height,
            candidates=[
                CandidateTx(
                    index=candidate_index if candidate_index is not None else 0,
                    txid=target_txid or "",
                    tweak_hex=tweak_hex,
                    output_pubkey_hex=output_pubkey_hex
                )
            ],
            b_scan_scalars=[b_scan_scalar] if b_scan_scalar is not None else None
        )
        return results[0]

    async def probe_batch(
        self,
        block_height: int,
        candidates: List[CandidateTx],
        b_scan_scalars: Optional[List[Optional[int]]] = None
    ) -> List[ProbeAuditResult]:
        """
        Probe multiple candidate tweaks concurrently in a single Frigate connection.

        Args:
            block_height: Block height to probe.
            candidates: List of CandidateTx to audit.
            b_scan_scalars: Optional list of scalars to use per candidate.

        Returns:
            List of ProbeAuditResult for each candidate.
        """
        start_time = time.time()
        results: List[ProbeAuditResult] = []

        if not candidates:
            return results

        # Derive keys for each candidate
        # derived_items: list of (candidate, scan_priv, spend_pub, target_hex, scalar)
        derived_items = []
        for i, cand in enumerate(candidates):
            scalar = b_scan_scalars[i] if (b_scan_scalars and i < len(b_scan_scalars)) else None
            try:
                scan_priv, spend_pub, target_hex = derive_canary_keys(
                    cand.tweak_hex, cand.output_pubkey_hex, scalar
                )
                derived_items.append((cand, scan_priv, spend_pub, target_hex))
            except Exception as e:
                results.append(ProbeAuditResult(
                    success=False,
                    matched=False,
                    block_height=block_height,
                    tweak_hex=cand.tweak_hex,
                    target_output_hex=cand.output_pubkey_hex,
                    candidate_index=cand.index,
                    target_txid=cand.txid,
                    error_message=f"Key derivation failed: {e}",
                    elapsed_time=time.time() - start_time
                ))

        if not derived_items:
            return results

        reader = None
        writer = None
        # Map address -> (candidate, scan_priv, spend_pub, history)
        addr_map: Dict[str, Dict[str, Any]] = {}

        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port),
                timeout=self.timeout
            )

            # Step 1: Handshake
            handshake = json.dumps({
                "jsonrpc": "2.0",
                "id": 1,
                "method": "server.version",
                "params": ["FrigateProbe", "1.4"]
            }) + "\n"
            writer.write(handshake.encode("utf-8"))
            await writer.drain()
            await asyncio.wait_for(reader.readline(), timeout=self.timeout)

            # Step 2: Send all subscriptions (using single-block range)
            range_param = f"{block_height}-{block_height}"
            for req_id, (cand, scan_priv, spend_pub, _) in enumerate(derived_items, start=2):
                sub_req = json.dumps({
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "method": "blockchain.silentpayments.subscribe",
                    "params": [scan_priv, spend_pub, range_param]
                }) + "\n"
                writer.write(sub_req.encode("utf-8"))
            await writer.drain()

            # Step 3: Read subscription confirmations
            pending_addresses = set()
            for _ in range(len(derived_items)):
                line = await asyncio.wait_for(reader.readline(), timeout=self.timeout)
                resp = json.loads(line.decode("utf-8"))
                req_id = resp.get("id")
                idx = req_id - 2
                cand, scan_priv, spend_pub, _ = derived_items[idx]
                if "error" in resp and resp["error"]:
                    addr_map[f"err_{idx}"] = {
                        "cand": cand,
                        "scan_priv": scan_priv,
                        "spend_pub": spend_pub,
                        "address": None,
                        "history": [],
                        "error": str(resp["error"])
                    }
                else:
                    addr = resp.get("result", {}).get("address")
                    addr_map[addr] = {
                        "cand": cand,
                        "scan_priv": scan_priv,
                        "spend_pub": spend_pub,
                        "address": addr,
                        "history": [],
                        "error": None
                    }
                    pending_addresses.add(addr)

            # Step 4: Listen for notifications until all subscriptions complete (progress >= 1.0)
            while pending_addresses:
                line = await asyncio.wait_for(reader.readline(), timeout=self.timeout)
                if not line:
                    break
                try:
                    msg = json.loads(line.decode("utf-8"))
                except json.JSONDecodeError:
                    continue

                if msg.get("method") == "blockchain.silentpayments.subscribe":
                    params = msg.get("params", {})
                    addr = None
                    hist = []
                    prog = 0.0

                    if isinstance(params, dict):
                        addr = params.get("subscription", {}).get("address")
                        hist = params.get("history", [])
                        prog = params.get("progress", 0.0)
                    elif isinstance(params, list) and len(params) >= 3:
                        sub_obj = params[0]
                        if isinstance(sub_obj, dict):
                            addr = sub_obj.get("address")
                        prog = params[1]
                        hist = params[2]

                    if addr and addr in addr_map:
                        if hist:
                            addr_map[addr]["history"].extend(hist)
                        if isinstance(prog, (int, float)) and prog >= 1.0:
                            pending_addresses.discard(addr)

            # Step 5: Clean up all subscriptions with unsubscribe
            for entry in addr_map.values():
                if entry.get("scan_priv") and entry.get("spend_pub"):
                    unsub_req = json.dumps({
                        "jsonrpc": "2.0",
                        "id": 9999,
                        "method": "blockchain.silentpayments.unsubscribe",
                        "params": [entry["scan_priv"], entry["spend_pub"]]
                    }) + "\n"
                    writer.write(unsub_req.encode("utf-8"))
            await writer.drain()

            total_elapsed = time.time() - start_time

            # Format final results
            for entry in addr_map.values():
                cand = entry["cand"]
                hist = entry["history"]
                err = entry["error"]
                matched = len(hist) > 0
                results.append(ProbeAuditResult(
                    success=(err is None),
                    matched=matched,
                    block_height=block_height,
                    tweak_hex=cand.tweak_hex,
                    target_output_hex=cand.output_pubkey_hex,
                    discovered_history=hist,
                    candidate_index=cand.index,
                    target_txid=cand.txid,
                    subscribed_address=entry.get("address"),
                    error_message=err,
                    elapsed_time=total_elapsed
                ))

            # Sort by candidate index
            results.sort(key=lambda r: r.candidate_index if r.candidate_index is not None else 0)
            return results

        except Exception as e:
            total_elapsed = time.time() - start_time
            # Return failure for any remaining items
            for cand, _, _, _ in derived_items:
                results.append(ProbeAuditResult(
                    success=False,
                    matched=False,
                    block_height=block_height,
                    tweak_hex=cand.tweak_hex,
                    target_output_hex=cand.output_pubkey_hex,
                    candidate_index=cand.index,
                    target_txid=cand.txid,
                    error_message=str(e),
                    elapsed_time=total_elapsed
                ))
            return results
        finally:
            if writer:
                writer.close()
                try:
                    await writer.wait_closed()
                except Exception:
                    pass


def main():
    parser = argparse.ArgumentParser(description="Frigate Silent Payments Canary Probe")
    parser.add_argument("block_height", type=int, nargs="?", default=None, help="Block height to probe")
    parser.add_argument("--height", type=int, default=None, help="Block height alias")
    parser.add_argument("--frigate", default=os.getenv("FRIGATE_ENDPOINT", "127.0.0.1:57001"),
                        help="Frigate server endpoint host:port (default: $FRIGATE_ENDPOINT or 127.0.0.1:57001)")
    parser.add_argument("--blindbit", default=os.getenv("BLINDBIT_GRPC_ENDPOINT"),
                        help="BlindBit gRPC endpoint host:port (default: $BLINDBIT_GRPC_ENDPOINT)")
    parser.add_argument("--index", type=int, default=None,
                        help="Specific candidate transaction index to audit (0-indexed)")
    parser.add_argument("--sample", type=int, default=None,
                        help="Number of candidate transactions to randomly sample and audit")
    parser.add_argument("--all", action="store_true",
                        help="Audit all candidate transactions in the block")
    parser.add_argument("--tweak", default=None, help="Explicit 33-byte hex tweak point (A_sum)")
    parser.add_argument("--output", default=None, help="Explicit 32-byte or 33-byte hex output pubkey")
    parser.add_argument("--txid", default=None, help="Optional expected transaction ID")
    parser.add_argument("--timeout", type=float, default=20.0, help="Socket timeout in seconds")

    args = parser.parse_args()

    height = args.block_height or args.height
    if height is None:
        print("Error: Block height is required. Example: just probe-frigate 850000 --sample 5")
        sys.exit(1)

    # Validate mutually exclusive options
    selection_flags = sum([args.index is not None, args.sample is not None, args.all])
    if selection_flags > 1:
        print("Error: Options --index, --sample, and --all are mutually exclusive. Please choose one.")
        sys.exit(1)

    candidates: List[CandidateTx] = []

    # Case 1: Explicit tweak and output passed via CLI
    if args.tweak and args.output:
        candidates = [CandidateTx(index=0, txid=args.txid or "", tweak_hex=args.tweak, output_pubkey_hex=args.output)]
    # Case 2: Query BlindBit gRPC for candidate transactions
    elif args.blindbit:
        print(f"[*] Querying BlindBit gRPC at {args.blindbit} for block {height}...")
        try:
            candidates = fetch_candidates_from_blindbit(args.blindbit, height)
            print(f"[*] Discovered {len(candidates)} eligible transactions with tweaks in block {height}.")
        except Exception as e:
            print(f"Error fetching from BlindBit gRPC: {e}")
            sys.exit(1)
    else:
        print("Error: Please provide --blindbit (or set BLINDBIT_GRPC_ENDPOINT), or supply --tweak and --output.")
        sys.exit(1)

    if not candidates:
        print(f"Error: No eligible transactions found in block {height}.")
        sys.exit(1)

    # Apply Selection Strategy: --index, --sample, --all, or default index 0
    selected_candidates: List[CandidateTx] = []
    if args.index is not None:
        if args.index < 0 or args.index >= len(candidates):
            print(f"Error: --index {args.index} out of range (block {height} has {len(candidates)} candidate transactions, indices 0..{len(candidates)-1}).")
            sys.exit(1)
        selected_candidates = [candidates[args.index]]
    elif args.sample is not None:
        sample_count = min(args.sample, len(candidates))
        selected_candidates = random.sample(candidates, sample_count)
        selected_candidates.sort(key=lambda c: c.index)
    elif args.all:
        selected_candidates = candidates
    else:
        # Default: first candidate
        selected_candidates = [candidates[0]]

    # Parse Frigate host and port
    if ":" in args.frigate:
        host, port_str = args.frigate.split(":")
        port = int(port_str)
    else:
        host = args.frigate
        port = 57001

    print(f"[*] Probing {len(selected_candidates)} candidate transaction(s) against Frigate at {host}:{port}...")
    client = FrigateProbeClient(host, port, timeout=args.timeout)

    # Batch in groups of 50 to respect Frigate's maxSubscriptions limit
    BATCH_SIZE = 50
    all_results: List[ProbeAuditResult] = []
    for i in range(0, len(selected_candidates), BATCH_SIZE):
        batch = selected_candidates[i:i + BATCH_SIZE]
        batch_results = asyncio.run(client.probe_batch(height, batch))
        all_results.extend(batch_results)

    # Print Summary & Audit Report
    total = len(all_results)
    passed = sum(1 for r in all_results if r.matched)
    failed = total - passed
    elapsed = max((r.elapsed_time for r in all_results), default=0.0)

    print(f"\n=== Frigate Canary Probe Audit for Block {height} ===")
    print(f"Frigate Endpoint: {host}:{port}")
    print(f"Total Audited:    {total} transaction(s) (Selected from {len(candidates)} total in block)")
    print(f"Passed (Matches): {passed}")
    print(f"Failed (0 hits):  {failed}")
    print(f"Elapsed Time:     {elapsed:.3f}s")

    if passed == total:
        print(f"Consensus Verdict: ALL MATCH (100% Agreement with BlindBit)")
    else:
        print(f"Consensus Verdict: MISMATCH ({passed}/{total} matched, {failed} failed)")

    print("\nDetailed Transaction Results:")
    for r in all_results:
        status = "MATCH" if r.matched else "MISMATCH"
        tx_label = f"tx {r.target_txid[:16]}..." if r.target_txid else "tx [unknown]"
        idx_label = f"[{r.candidate_index}]" if r.candidate_index is not None else "[0]"
        hits_label = f"{len(r.discovered_history)} hit(s)" if r.matched else "0 hits"
        print(f"  {idx_label} {tx_label}: {status} ({hits_label})")
        if not r.matched and r.error_message:
            print(f"       Error: {r.error_message}")

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
