"""
Silent Payments Tweak Service Auditor
Main auditor class that coordinates multiple indexing services
"""
import asyncio
import logging
from typing import List
import time

from models import ServiceConfig, AuditResult, RangeAuditResult, ServiceResult
from service_interface import IndexServiceInterface
from service_implementations import create_service_instance
from rate_limiter import RangeAuditRateLimiter


class TweakServiceAuditor:
    """Main auditor class for Silent Payments tweak services"""
    
    def __init__(self, services: List[ServiceConfig], enable_rate_limiting: bool = True, 
                 inter_block_delay: float = 0.0001):
        """
        Initialize the auditor with a list of service configurations
        
        Args:
            services: List of ServiceConfig objects
            enable_rate_limiting: Whether to enable rate limiting (default: True)
            inter_block_delay: Delay between blocks in range audits (default: 0.0001s)
        """
        self.services = services
        self.service_instances: List[IndexServiceInterface] = []
        self.logger = logging.getLogger("auditor")
        self.enable_rate_limiting = enable_rate_limiting
        
        # Initialize rate limiter
        self.rate_limiter = RangeAuditRateLimiter(inter_block_delay=inter_block_delay)
        
        # Initialize service instances using factory function
        for config in services:
            if config.active:
                service_instance = create_service_instance(config)
                self.service_instances.append(service_instance)
                
                # Configure rate limiting for this service
                if enable_rate_limiting:
                    self.rate_limiter.configure_service(
                        config.name, 
                        config.requests_per_second
                    )
        
        self.logger.info(f"Initialized auditor with {len(self.service_instances)} services")
        if enable_rate_limiting:
            self.logger.info("Rate limiting enabled")
    
    async def audit_block(self, block_height: int) -> AuditResult:
        """
        Audit a single block across all configured services
        
        Args:
            block_height: The block height to audit
            
        Returns:
            AuditResult containing results from all services
        """
        self.logger.info(f"Starting audit for block {block_height}")
        start_time = time.time()
        
        # Create rate-limited tasks for each service
        tasks = []
        for service in self.service_instances:
            if self.enable_rate_limiting:
                task = self._rate_limited_service_call(service, block_height)
            else:
                task = service.get_tweaks_for_block(block_height)
            tasks.append(task)
        
        # Wait for all services to complete
        service_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Handle any exceptions
        processed_results = []
        for i, result in enumerate(service_results):
            if isinstance(result, Exception):
                self.logger.error(f"Service {self.services[i].name} failed with exception: {result}")
                # Create a failed ServiceResult
                failed_result = ServiceResult(
                    service_name=self.services[i].name,
                    block_height=block_height,
                    tweaks=[],
                    request_time=0.0,
                    success=False,
                    error_message=str(result)
                )
                processed_results.append(failed_result)
            else:
                processed_results.append(result)
        
        audit_result = AuditResult(
            block_height=block_height,
            service_results=processed_results,
            total_services=len(self.service_instances),
            successful_services=sum(1 for r in processed_results if r.success)
        )
        
        total_time = time.time() - start_time
        self.logger.info(f"Completed audit for block {block_height} in {total_time:.2f}s")
        self._log_audit_summary(audit_result)
        
        return audit_result
    
    async def _rate_limited_service_call(self, service: IndexServiceInterface, block_height: int) -> ServiceResult:
        """
        Make a rate-limited call to a service
        
        Args:
            service: The service instance to call
            block_height: The block height to audit
            
        Returns:
            ServiceResult from the service
        """
        # Get the service name from the config
        service_name = service.config.name
        
        # Acquire rate limit token
        await self.rate_limiter.acquire_service_token(service_name)
        
        # Make the actual service call
        return await service.get_tweaks_for_block(block_height)

    async def audit_range(self, start_block: int, end_block: int) -> RangeAuditResult:
        """
        Audit a range of blocks
        
        Args:
            start_block: Starting block height (inclusive)
            end_block: Ending block height (inclusive)
            
        Returns:
            RangeAuditResult containing results for all blocks in range
        """
        self.logger.info(f"Starting range audit from block {start_block} to {end_block}")
        
        if start_block > end_block:
            raise ValueError("Start block must be <= end block")
        
        block_results = []
        
        for block_height in range(start_block, end_block + 1):
            try:
                result = await self.audit_block(block_height)
                block_results.append(result)
            except Exception as e:
                self.logger.error(f"Failed to audit block {block_height}: {e}")
                # Continue with next block
                continue
        
        range_result = RangeAuditResult(
            start_block=start_block,
            end_block=end_block,
            block_results=block_results
        )
        
        self.logger.info(f"Completed range audit: {len(block_results)} blocks processed")
        self._log_range_summary(range_result)
        
        return range_result
    
    def _log_audit_summary(self, audit_result: AuditResult):
        """Log summary of single block audit"""
        self.logger.info(f"Block {audit_result.block_height} audit summary:")
        self.logger.info(f"  Services: {audit_result.successful_services}/{audit_result.total_services} successful")
        
        # Log tweak counts
        for service_name, count in audit_result.tweak_counts.items():
            self.logger.info(f"  {service_name}: {count} tweaks")
        
        # Log matching information
        matching_count = len(audit_result.matching_tweaks)
        self.logger.info(f"  Matching tweaks across all services: {matching_count}")
        
        # Log non-matching by service
        non_matching = audit_result.non_matching_by_service
        for service_name, non_matching_tweaks in non_matching.items():
            if non_matching_tweaks:
                self.logger.info(f"  {service_name} unique tweaks: {len(non_matching_tweaks)}")
    
    def _log_range_summary(self, range_result: RangeAuditResult):
        """Log summary of range audit"""
        self.logger.info(f"Range audit summary (blocks {range_result.start_block}-{range_result.end_block}):")
        self.logger.info(f"  Total blocks processed: {range_result.total_blocks_audited}")
        
        summary = range_result.summary_by_service
        for service_name, stats in summary.items():
            self.logger.info(
                f"  {service_name}: {stats['total_tweaks']} total tweaks, "
                f"{stats['blocks_processed']} blocks processed, "
                f"{stats['failures']} failures"
            )