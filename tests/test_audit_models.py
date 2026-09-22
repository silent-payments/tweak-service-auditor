"""
Unit tests for data models, focusing on AuditResult.matching_tweaks intersection logic.
"""
import unittest
from models import AuditResult, ServiceResult, TweakData, ServicePair


class TestAuditResultMatching(unittest.TestCase):
    def _make_tweak(self, h: str) -> TweakData:
        return TweakData(
            tweak_hash=h,
            block_height=100,
            transaction_id="txid",
            output_index=0
        )

    def test_matching_tweaks_empty_results(self):
        audit = AuditResult(
            block_height=100,
            service_results=[],
            total_services=0,
            successful_services=0
        )
        self.assertEqual(audit.matching_tweaks, set())

    def test_matching_tweaks_single_service(self):
        sr = ServiceResult(
            service_name="service_a",
            block_height=100,
            tweaks=[self._make_tweak("tweak1"), self._make_tweak("tweak2")],
            request_time=0.1,
            success=True
        )
        audit = AuditResult(
            block_height=100,
            service_results=[sr],
            total_services=1,
            successful_services=1
        )
        self.assertEqual(audit.matching_tweaks, {"tweak1", "tweak2"})

    def test_matching_tweaks_all_match(self):
        sr1 = ServiceResult(
            service_name="service_a",
            block_height=100,
            tweaks=[self._make_tweak("t1"), self._make_tweak("t2")],
            request_time=0.1,
            success=True
        )
        sr2 = ServiceResult(
            service_name="service_b",
            block_height=100,
            tweaks=[self._make_tweak("t1"), self._make_tweak("t2")],
            request_time=0.1,
            success=True
        )
        audit = AuditResult(
            block_height=100,
            service_results=[sr1, sr2],
            total_services=2,
            successful_services=2
        )
        self.assertEqual(audit.matching_tweaks, {"t1", "t2"})

    def test_matching_tweaks_partial_intersection(self):
        sr1 = ServiceResult(
            service_name="service_a",
            block_height=100,
            tweaks=[self._make_tweak("t1"), self._make_tweak("t2"), self._make_tweak("t3")],
            request_time=0.1,
            success=True
        )
        sr2 = ServiceResult(
            service_name="service_b",
            block_height=100,
            tweaks=[self._make_tweak("t2"), self._make_tweak("t3"), self._make_tweak("t4")],
            request_time=0.1,
            success=True
        )
        sr3 = ServiceResult(
            service_name="service_c",
            block_height=100,
            tweaks=[self._make_tweak("t2"), self._make_tweak("t5")],
            request_time=0.1,
            success=True
        )
        audit = AuditResult(
            block_height=100,
            service_results=[sr1, sr2, sr3],
            total_services=3,
            successful_services=3
        )
        # Only t2 appears in all three
        self.assertEqual(audit.matching_tweaks, {"t2"})
        self.assertEqual(audit.non_matching_by_service["service_a"], {"t1", "t3"})
        self.assertEqual(audit.non_matching_by_service["service_b"], {"t3", "t4"})
        self.assertEqual(audit.non_matching_by_service["service_c"], {"t5"})

    def test_matching_tweaks_ignores_failed_services(self):
        sr1 = ServiceResult(
            service_name="service_a",
            block_height=100,
            tweaks=[self._make_tweak("t1"), self._make_tweak("t2")],
            request_time=0.1,
            success=True
        )
        sr2 = ServiceResult(
            service_name="service_b",
            block_height=100,
            tweaks=[],
            request_time=0.1,
            success=False,
            error_message="timeout"
        )
        sr3 = ServiceResult(
            service_name="service_c",
            block_height=100,
            tweaks=[self._make_tweak("t1"), self._make_tweak("t3")],
            request_time=0.1,
            success=True
        )
        audit = AuditResult(
            block_height=100,
            service_results=[sr1, sr2, sr3],
            total_services=3,
            successful_services=2
        )
        self.assertEqual(audit.matching_tweaks, {"t1"})


if __name__ == "__main__":
    unittest.main()
