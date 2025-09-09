"""
Base interface and implementations for Silent Payments indexing services
"""
from abc import ABC, abstractmethod
import time
import logging
from typing import List, Dict, Any
import aiohttp

from models import ServiceConfig, ServiceResult, TweakData, ServiceType
from socket_client import AsyncConnection


class IndexServiceInterface(ABC):
    """Abstract base class for all indexing services"""
    
    def __init__(self, config: ServiceConfig):
        self.config = config
        self.logger = logging.getLogger(f"service.{config.name}")
    
    @abstractmethod
    async def get_tweaks_for_block(self, block_height: int) -> ServiceResult:
        """
        Get tweaks for a specific block height
        
        Args:
            block_height: The block height to query
            
        Returns:
            ServiceResult containing the tweaks and metadata
        """
        pass
    
    @abstractmethod
    def _normalize_response(self, raw_response: Any, block_height: int) -> List[TweakData]:
        """
        Normalize the service-specific response to TweakData objects
        
        Args:
            raw_response: Raw response from the service
            block_height: Block height for context
            
        Returns:
            List of normalized TweakData objects
        """
        pass


class HTTPIndexService(IndexServiceInterface):
    """HTTP-based indexing service implementation"""
    
    def __init__(self, config: ServiceConfig):
        super().__init__(config)
        if config.service_type != ServiceType.HTTP:
            raise ValueError(f"HTTPIndexService requires HTTP service type, got {config.service_type}")
    
    async def get_tweaks_for_block(self, block_height: int) -> ServiceResult:
        """Get tweaks via HTTP request"""
        start_time = time.time()
        
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.config.timeout)) as session:
                url = self._build_url(block_height)
                headers = self.config.headers or {}
                
                self.logger.debug(f"Making HTTP request to {url}")
                
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        raw_data = await response.json()
                        tweaks = self._normalize_response(raw_data, block_height)
                        
                        return ServiceResult(
                            service_name=self.config.name,
                            block_height=block_height,
                            tweaks=tweaks,
                            request_time=time.time() - start_time,
                            success=True
                        )
                    else:
                        error_msg = f"HTTP {response.status}: {await response.text()}"
                        self.logger.error(f"HTTP request failed: {error_msg}")
                        
                        return ServiceResult(
                            service_name=self.config.name,
                            block_height=block_height,
                            tweaks=[],
                            request_time=time.time() - start_time,
                            success=False,
                            error_message=error_msg
                        )
        
        except Exception as e:
            error_msg = f"HTTP request error: {str(e)}"
            self.logger.error(error_msg)
            
            return ServiceResult(
                service_name=self.config.name,
                block_height=block_height,
                tweaks=[],
                request_time=time.time() - start_time,
                success=False,
                error_message=error_msg
            )
    
    def _build_url(self, block_height: int) -> str:
        """Build the URL for the request - to be overridden by specific implementations"""
        return f"{self.config.endpoint}/block/{block_height}/tweaks"
    
    def _normalize_response(self, raw_response: Any, block_height: int) -> List[TweakData]:
        """Default normalization - to be overridden by specific implementations"""
        # This is a placeholder implementation
        # Each specific service will override this method
        tweaks = []
        
        if isinstance(raw_response, dict) and 'tweaks' in raw_response:
            for tweak_data in raw_response['tweaks']:
                tweak = TweakData(
                    tweak_hash=tweak_data.get('hash', ''),
                    block_height=block_height,
                    transaction_id=tweak_data.get('txid', ''),
                    output_index=tweak_data.get('output_index', 0),
                    raw_data=tweak_data
                )
                tweaks.append(tweak)
        
        return tweaks


class RPCIndexService(IndexServiceInterface):
    """RPC-based indexing service implementation"""
    
    def __init__(self, config: ServiceConfig):
        super().__init__(config)
        if config.service_type != ServiceType.RPC:
            raise ValueError(f"RPCIndexService requires RPC service type, got {config.service_type}")
    
    async def get_tweaks_for_block(self, block_height: int) -> ServiceResult:
        """Get tweaks via RPC request"""
        start_time = time.time()
        
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.config.timeout)) as session:
                rpc_payload = self._build_rpc_payload(block_height)
                headers = {'Content-Type': 'application/json'}
                if self.config.headers:
                    headers.update(self.config.headers)
                
                self.logger.debug(f"Making RPC request to {self.config.endpoint}")
                
                async with session.post(
                    self.config.endpoint, 
                    json=rpc_payload,
                    headers=headers
                ) as response:
                    if response.status == 200:
                        raw_data = await response.json()
                        
                        if 'error' in raw_data and raw_data['error']:
                            error_msg = f"RPC error: {raw_data['error']}"
                            self.logger.error(error_msg)
                            
                            return ServiceResult(
                                service_name=self.config.name,
                                block_height=block_height,
                                tweaks=[],
                                request_time=time.time() - start_time,
                                success=False,
                                error_message=error_msg
                            )
                        
                        tweaks = self._normalize_response(raw_data.get('result', {}), block_height)
                        
                        return ServiceResult(
                            service_name=self.config.name,
                            block_height=block_height,
                            tweaks=tweaks,
                            request_time=time.time() - start_time,
                            success=True
                        )
                    else:
                        error_msg = f"RPC HTTP {response.status}: {await response.text()}"
                        self.logger.error(error_msg)
                        
                        return ServiceResult(
                            service_name=self.config.name,
                            block_height=block_height,
                            tweaks=[],
                            request_time=time.time() - start_time,
                            success=False,
                            error_message=error_msg
                        )
        
        except Exception as e:
            error_msg = f"RPC request error: {str(e)}"
            self.logger.error(error_msg)
            
            return ServiceResult(
                service_name=self.config.name,
                block_height=block_height,
                tweaks=[],
                request_time=time.time() - start_time,
                success=False,
                error_message=error_msg
            )
    
    def _build_rpc_payload(self, block_height: int) -> Dict[str, Any]:
        """Build RPC payload - to be overridden by specific implementations"""
        return {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getblocktweaks",
            "params": [block_height]
        }
    
    def _normalize_response(self, raw_response: Any, block_height: int) -> List[TweakData]:
        """Default normalization - to be overridden by specific implementations"""
        # This is a placeholder implementation
        # Each specific service will override this method
        tweaks = []
        
        if isinstance(raw_response, list):
            for tweak_data in raw_response:
                tweak = TweakData(
                    tweak_hash=tweak_data.get('hash', ''),
                    block_height=block_height,
                    transaction_id=tweak_data.get('txid', ''),
                    output_index=tweak_data.get('vout', 0),
                    raw_data=tweak_data
                )
                tweaks.append(tweak)
        
        return tweaks


class SocketRPCIndexService(IndexServiceInterface):
    """Socket-based RPC indexing service implementation (for Electrs)"""
    
    def __init__(self, config: ServiceConfig):
        super().__init__(config)
        if config.service_type != ServiceType.SOCKET_RPC:
            raise ValueError(f"SocketRPCIndexService requires SOCKET_RPC service type, got {config.service_type}")
        
        # Extract host and port from config
        if config.host and config.port:
            self.host = config.host
            self.port = config.port
        elif config.endpoint:
            # Try to parse from endpoint format like "127.0.0.1:60601"
            try:
                if '://' in config.endpoint:
                    # Remove protocol if present
                    endpoint = config.endpoint.split('://', 1)[1]
                else:
                    endpoint = config.endpoint
                
                if ':' in endpoint:
                    self.host, port_str = endpoint.rsplit(':', 1)
                    self.port = int(port_str)
                else:
                    raise ValueError("Port not specified")
            except (ValueError, IndexError):
                raise ValueError(f"Invalid endpoint format for socket RPC: {config.endpoint}. Use 'host:port' format")
        else:
            raise ValueError("Either 'host' and 'port' or 'endpoint' must be specified for socket RPC")
    
    async def get_tweaks_for_block(self, block_height: int) -> ServiceResult:
        """Get tweaks via socket RPC request"""
        start_time = time.time()
        
        try:
            self.logger.debug(f"Making socket RPC request to {self.host}:{self.port}")
            
            async with AsyncConnection((self.host, self.port)) as conn:
                method, params = self._build_rpc_call(block_height)
                response = await conn.call(method, *params)
                
                if 'error' in response and response['error']:
                    error_msg = f"Socket RPC error: {response['error']}"
                    self.logger.error(error_msg)
                    
                    return ServiceResult(
                        service_name=self.config.name,
                        block_height=block_height,
                        tweaks=[],
                        request_time=time.time() - start_time,
                        success=False,
                        error_message=error_msg
                    )
                
                tweaks = self._normalize_response(response.get('result', []), block_height)
                
                return ServiceResult(
                    service_name=self.config.name,
                    block_height=block_height,
                    tweaks=tweaks,
                    request_time=time.time() - start_time,
                    success=True
                )
        
        except Exception as e:
            error_msg = f"Socket RPC request error: {str(e)}"
            self.logger.error(error_msg)
            
            return ServiceResult(
                service_name=self.config.name,
                block_height=block_height,
                tweaks=[],
                request_time=time.time() - start_time,
                success=False,
                error_message=error_msg
            )
    
    def _build_rpc_call(self, block_height: int) -> tuple:
        """Build RPC method and parameters - to be overridden by specific implementations"""
        return 'blockchain.block.tweaks', [block_height]
    
    def _normalize_response(self, raw_response: Any, block_height: int) -> List[TweakData]:
        """Default normalization - to be overridden by specific implementations"""
        # This is a placeholder implementation
        # Each specific service will override this method
        tweaks = []
        
        if isinstance(raw_response, list):
            for tweak_data in raw_response:
                if isinstance(tweak_data, str):
                    # Simple string response - just the tweak hash
                    tweak = TweakData(
                        tweak_hash=tweak_data,
                        block_height=block_height,
                        transaction_id='',
                        output_index=0,
                        raw_data={'tweak': tweak_data}
                    )
                    tweaks.append(tweak)
                elif isinstance(tweak_data, dict):
                    # Dictionary response with more details
                    tweak = TweakData(
                        tweak_hash=tweak_data.get('tweak', tweak_data.get('hash', '')),
                        block_height=block_height,
                        transaction_id=tweak_data.get('txid', ''),
                        output_index=tweak_data.get('vout', 0),
                        raw_data=tweak_data
                    )
                    tweaks.append(tweak)
        
        return tweaks


class GRPCIndexService(IndexServiceInterface):
    """gRPC-based indexing service implementation"""
    
    def __init__(self, config: ServiceConfig):
        super().__init__(config)
        if config.service_type != ServiceType.GRPC:
            raise ValueError(f"GRPCIndexService requires GRPC service type, got {config.service_type}")
        
        # Extract host and port from config
        if config.host and config.port:
            self.host = config.host
            self.port = config.port
            self.target = f"{self.host}:{self.port}"
        elif config.endpoint:
            # Try to parse from endpoint format like "127.0.0.1:50051"
            try:
                if '://' in config.endpoint:
                    # Remove protocol if present
                    endpoint = config.endpoint.split('://', 1)[1]
                else:
                    endpoint = config.endpoint
                
                if ':' in endpoint:
                    self.host, port_str = endpoint.rsplit(':', 1)
                    self.port = int(port_str)
                    self.target = f"{self.host}:{self.port}"
                else:
                    raise ValueError("Port not specified")
            except (ValueError, IndexError):
                raise ValueError(f"Invalid endpoint format for gRPC: {config.endpoint}. Use 'host:port' format")
        else:
            raise ValueError("Either 'host' and 'port' or 'endpoint' must be specified for gRPC")
        
        self.channel = None
    
    async def get_tweaks_for_block(self, block_height: int) -> ServiceResult:
        """Get tweaks via gRPC request - to be implemented by specific gRPC services"""
        raise NotImplementedError("Subclasses must implement get_tweaks_for_block")
    
    def _get_channel(self):
        """Get or create a gRPC channel"""
        import grpc
        
        if self.channel is None:
            # Create insecure channel for now (no auth requirement from user)
            self.channel = grpc.insecure_channel(self.target)
        return self.channel
    
    def _close_channel(self):
        """Close the gRPC channel"""
        if hasattr(self, 'channel') and self.channel:
            self.channel.close()
            self.channel = None
    
    def _normalize_response(self, raw_response: Any, block_height: int) -> List[TweakData]:
        """Default normalization - to be overridden by specific implementations"""
        # This is a placeholder implementation
        # Each specific gRPC service will override this method
        tweaks = []
        
        # Handle protobuf response format
        if hasattr(raw_response, 'tweaks'):
            for i, tweak_bytes in enumerate(raw_response.tweaks):
                tweak = TweakData(
                    tweak_hash=tweak_bytes.hex() if isinstance(tweak_bytes, bytes) else str(tweak_bytes),
                    block_height=block_height,
                    transaction_id='',  # Not available in basic tweak response
                    output_index=i,     # Use index as placeholder
                    raw_data={'tweak_bytes': tweak_bytes}
                )
                tweaks.append(tweak)
        
        return tweaks
