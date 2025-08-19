"""
Data models for Silent Payments Tweak Service Auditor
"""
from dataclasses import dataclass
from typing import List, Set, Dict, Optional, Any
from enum import Enum


class ServiceType(Enum):
    """Types of indexing services"""
    DEFAULT = None
    HTTP = "http"
    RPC = "rpc"
    SOCKET_RPC = "socket_rpc"
    GRPC = "grpc"


@dataclass
class ServicePair:
    """Configuration for a service pair comparison"""
    name: str
    service1: str
    service2: str
    active: bool = True


@dataclass
class TweakData:
    """Normalized tweak data structure"""
    tweak_hash: str
    block_height: int
    transaction_id: str
    output_index: int
    raw_data: Optional[Dict[str, Any]] = None


@dataclass
class ServiceConfig:
    """Configuration for an indexing service"""
    name: str
    service_type: ServiceType
    endpoint: str
    auth: Optional[Dict[str, str]] = None
    headers: Optional[Dict[str, str]] = None
    timeout: int = 5
    host: Optional[str] = None  # For socket-based services
    port: Optional[int] = None  # For socket-based services
    cookie_file: Optional[str] = None  # For cookie-based authentication
    active: bool = False
    requests_per_second: float = 200.0  # Max requests per second for this service
    filter_spent: Optional[bool] = None  # For bitcoin & blindbit: whether to filter spent outputs
    dust_limit: Optional[int] = None  # For bitcoin & blindbit: dust limit threshold


@dataclass
class ServiceResult:
    """Result from a single indexing service"""
    service_name: str
    block_height: int
    tweaks: List[TweakData]
    request_time: float
    success: bool
    error_message: Optional[str] = None


@dataclass
class PairwiseComparison:
    """Result of comparing two services"""
    pair_name: str
    service1_name: str
    service2_name: str
    service1_tweaks: Set[str]
    service2_tweaks: Set[str]
    matching_tweaks: Set[str]
    service1_unique: Set[str]
    service2_unique: Set[str]
    
    @property
    def match_percentage(self) -> float:
        """Calculate percentage of matching tweaks"""
        total_unique = len(self.service1_tweaks | self.service2_tweaks)
        if total_unique == 0:
            return 100.0
        return (len(self.matching_tweaks) / total_unique) * 100.0


@dataclass
class AuditResult:
    """Complete audit result for a block or range"""
    block_height: int
    service_results: List[ServiceResult]
    total_services: int
    successful_services: int
    
    @property
    def tweak_counts(self) -> Dict[str, int]:
        """Get tweak count per service"""
        return {
            result.service_name: len(result.tweaks) 
            for result in self.service_results if result.success
        }
    
    @property
    def matching_tweaks(self) -> Set[str]:
        """Get tweaks that match across all successful services"""
        if not self.service_results:
            return set()
        
        successful_results = [r for r in self.service_results if r.success]
        if len(successful_results) < 2:
            return set()
        
        all_tweaks = set()
        for result in successful_results:
            all_tweaks.update(tweak.tweak_hash for tweak in result.tweaks)

        matching = set()
        # Find intersection with all other services
        for result in successful_results:
            service_tweaks = {tweak.tweak_hash for tweak in result.tweaks}
            matching = all_tweaks.intersection(service_tweaks)
        
        return matching
    
    @property
    def non_matching_by_service(self) -> Dict[str, Set[str]]:
        """Get non-matching tweaks by service"""
        matching = self.matching_tweaks
        non_matching = {}
        
        for result in self.service_results:
            if result.success:
                service_tweaks = {tweak.tweak_hash for tweak in result.tweaks}
                non_matching[result.service_name] = service_tweaks - matching
        
        return non_matching

    @property
    def total_request_time_by_service(self) -> Dict[str, float]:
        """Sum of request_time for each service (for this block)"""
        times = {}
        for result in self.service_results:
            if result.success:
                times[result.service_name] = times.get(result.service_name, 0.0) + result.request_time
        return times

    def pairwise_comparisons(self, pairs: List[ServicePair]) -> List[PairwiseComparison]:
        """
        For each configured service pair, compute unique/matching tweaks between the two services.
        Returns a list of PairwiseComparison objects.
        """
        # Build a lookup of service_name -> set of tweak_hashes (for successful services only)
        service_tweaks = {
            r.service_name: {t.tweak_hash for t in r.tweaks}
            for r in self.service_results if r.success
        }
        results = []
        for pair in pairs:
            if not pair.active:
                continue
            s1 = pair.service1
            s2 = pair.service2
            tweaks1 = service_tweaks.get(s1, set())
            tweaks2 = service_tweaks.get(s2, set())
            matching = tweaks1 & tweaks2
            unique1 = tweaks1 - tweaks2
            unique2 = tweaks2 - tweaks1
            results.append(PairwiseComparison(
                pair_name=pair.name,
                service1_name=s1,
                service2_name=s2,
                service1_tweaks=tweaks1,
                service2_tweaks=tweaks2,
                matching_tweaks=matching,
                service1_unique=unique1,
                service2_unique=unique2
            ))
        return results


@dataclass 
class RangeAuditResult:
    """Audit result for a range of blocks"""
    start_block: int
    end_block: int
    block_results: List[AuditResult]
    
    @property
    def total_blocks_audited(self) -> int:
        return len(self.block_results)
    
    @property
    def summary_by_service(self) -> Dict[str, Dict[str, int]]:
        """Summary statistics by service across all blocks"""
        summary = {}
        
        for block_result in self.block_results:
            for result in block_result.service_results:
                if result.service_name not in summary:
                    summary[result.service_name] = {
                        'total_tweaks': 0,
                        'blocks_processed': 0,
                        'failures': 0,
                        'total_request_time': 0.0
                    }
                
                if result.success:
                    summary[result.service_name]['total_tweaks'] += len(result.tweaks)
                    summary[result.service_name]['blocks_processed'] += 1
                    summary[result.service_name]['total_request_time'] += result.request_time
                else:
                    summary[result.service_name]['failures'] += 1
        
        return summary

    @property
    def total_request_time_by_service(self) -> Dict[str, float]:
        """Sum of request_time for each service across all blocks"""
        times = {}
        for block_result in self.block_results:
            for service_name, t in block_result.total_request_time_by_service.items():
                times[service_name] = times.get(service_name, 0.0) + t
        return times
