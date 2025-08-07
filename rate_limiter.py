"""
Rate limiting utilities for the Silent Payments Tweak Service Auditor
"""
import asyncio
import time
from typing import Dict
from dataclasses import dataclass


@dataclass
class RateLimiterState:
    """State for a single service's rate limiter"""
    tokens: float
    last_update: float
    refill_rate: float  # tokens per second


class ServiceRateLimiter:
    """
    Token bucket rate limiter for individual services
    Prevents overwhelming services with too many concurrent requests
    """
    
    def __init__(self):
        """Initialize rate limiter"""
        self.limiters: Dict[str, RateLimiterState] = {}
    
    def add_service(self, service_name: str, requests_per_second: float):
        """
        Add a service to the rate limiter
        
        Args:
            service_name: Name of the service
            requests_per_second: Maximum requests per second allowed
        """
        self.limiters[service_name] = RateLimiterState(
            tokens=1.0,  # Start with one token available
            last_update=time.time(),
            refill_rate=requests_per_second
        )
    
    async def acquire(self, service_name: str) -> bool:
        """
        Acquire a token for the service (blocking if necessary)
        
        Args:
            service_name: Name of the service
            
        Returns:
            True when token is acquired
        """
        if service_name not in self.limiters:
            # No rate limiting configured for this service
            return True
        
        limiter = self.limiters[service_name]
        
        while True:
            now = time.time()
            time_passed = now - limiter.last_update
            
            # Add tokens based on time passed
            tokens_to_add = time_passed * limiter.refill_rate
            limiter.tokens = min(1.0, limiter.tokens + tokens_to_add)
            limiter.last_update = now
            
            if limiter.tokens >= 1.0:
                # Token available, consume it
                limiter.tokens -= 1.0
                return True
            else:
                # Need to wait for next token
                time_to_wait = (1.0 - limiter.tokens) / limiter.refill_rate
                await asyncio.sleep(min(time_to_wait, 1.0))  # Cap wait time at 1 second
    
    def get_status(self, service_name: str) -> Dict[str, float]:
        """
        Get current status of the rate limiter for a service
        
        Args:
            service_name: Name of the service
            
        Returns:
            Dictionary with current tokens and refill rate
        """
        if service_name not in self.limiters:
            return {"tokens": float('inf'), "refill_rate": float('inf')}
        
        limiter = self.limiters[service_name]
        now = time.time()
        time_passed = now - limiter.last_update
        tokens_to_add = time_passed * limiter.refill_rate
        current_tokens = min(1.0, limiter.tokens + tokens_to_add)
        
        return {
            "tokens": current_tokens,
            "refill_rate": limiter.refill_rate
        }


class RangeAuditRateLimiter:
    """
    Rate limiter for range audits to prevent overwhelming services
    Provides both per-service rate limiting and global pacing
    """
    
    def __init__(self, inter_block_delay: float = 0.1):
        """
        Initialize range audit rate limiter
        
        Args:
            inter_block_delay: Delay between processing blocks (seconds)
        """
        self.service_limiter = ServiceRateLimiter()
        self.inter_block_delay = inter_block_delay
        self.concurrent_limit = asyncio.Semaphore(10)  # Limit concurrent block processing
    
    def configure_service(self, service_name: str, requests_per_second: float):
        """Configure rate limiting for a service"""
        self.service_limiter.add_service(service_name, requests_per_second)
    
    async def acquire_service_token(self, service_name: str):
        """Acquire a token for a service request"""
        await self.service_limiter.acquire(service_name)
    
    async def acquire_block_slot(self):
        """Acquire a slot for processing a block"""
        await self.concurrent_limit.acquire()
    
    def release_block_slot(self):
        """Release a block processing slot"""
        self.concurrent_limit.release()
    
    async def inter_block_wait(self):
        """Wait between processing blocks"""
        if self.inter_block_delay > 0:
            await asyncio.sleep(self.inter_block_delay)
    
    def get_service_status(self, service_name: str) -> Dict[str, float]:
        """Get rate limiter status for a service"""
        return self.service_limiter.get_status(service_name)
