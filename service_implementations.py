"""
Example implementations of specific indexing services
These demonstrate how to extend the base HTTP and RPC service classes
"""
import time
import aiohttp
import os
import json
from pathlib import Path
from typing import List, Dict, Any, Union
from service_interface import HTTPIndexService, RPCIndexService, SocketRPCIndexService, GRPCIndexService, IndexServiceInterface
from models import TweakData, ServiceConfig, ServiceType, ServiceResult


class ExampleHTTPService(HTTPIndexService):
    """Example HTTP-based indexing service"""
    
    def _build_url(self, block_height: int) -> str:
        """Build service-specific URL"""
        return f"{self.config.endpoint}/api/v1/silent-payments/block/{block_height}"
    
    def _normalize_response(self, raw_response: Any, block_height: int) -> List[TweakData]:
        """Normalize this service's response format"""
        tweaks = []
        
        if isinstance(raw_response, dict) and 'silent_payment_tweaks' in raw_response:
            for tweak_data in raw_response['silent_payment_tweaks']:
                tweak = TweakData(
                    tweak_hash=tweak_data.get('tweak', ''),
                    block_height=block_height,
                    transaction_id=tweak_data.get('transaction_hash', ''),
                    output_index=tweak_data.get('output_index', 0),
                    raw_data=tweak_data
                )
                tweaks.append(tweak)
        
        return tweaks


class ExampleRPCService(RPCIndexService):
    """Example RPC-based indexing service"""
    
    def _build_rpc_payload(self, block_height: int) -> Dict[str, Any]:
        """Build service-specific RPC payload"""
        return {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "silent_payments_get_tweaks",
            "params": {
                "block_height": block_height,
                "include_raw": True
            }
        }
    
    def _normalize_response(self, raw_response: Any, block_height: int) -> List[TweakData]:
        """Normalize this service's response format"""
        tweaks = []
        
        if isinstance(raw_response, dict) and 'tweaks' in raw_response:
            for tweak_data in raw_response['tweaks']:
                tweak = TweakData(
                    tweak_hash=tweak_data.get('hash', ''),
                    block_height=block_height,
                    transaction_id=tweak_data.get('tx_id', ''),
                    output_index=tweak_data.get('vout', 0),
                    raw_data=tweak_data
                )
                tweaks.append(tweak)
        
        return tweaks


class BitcoinCoreRPCService(RPCIndexService):
    """Bitcoin Core RPC service implementation"""
    
    def _get_cookie_auth(self) -> aiohttp.BasicAuth:
        """
        Read Bitcoin Core cookie file and return BasicAuth for aiohttp
        
        Returns:
            aiohttp.BasicAuth object if cookie file exists and is readable, None otherwise
        """
        if not self.config.cookie_file:
            return None
            
        # Expand user path if needed (e.g., ~ to home directory)
        cookie_path = os.path.expanduser(self.config.cookie_file)
        
        if os.path.exists(cookie_path):
            try:
                # Read the cookie file
                with open(cookie_path, 'r') as f:
                    cookie_content = f.read().strip()
                
                # Bitcoin Core cookie format is "username:password"
                if ':' in cookie_content:
                    username, password = cookie_content.split(':', 1)
                    self.logger.debug(f"Successfully loaded cookie authentication for user: {username}")
                    return aiohttp.BasicAuth(login=username, password=password)
                else:
                    self.logger.warning(f"Invalid cookie file format in {cookie_path}")
                    return None
                    
            except Exception as e:
                self.logger.error(f"Failed to read cookie file {cookie_path}: {e}")
                return None
        else:
            self.logger.error(f"Cannot find cookie file {cookie_path}")
            return None

    async def get_tweaks_for_block(self, block_height: int) -> ServiceResult:
        """Get tweaks via Bitcoin Core RPC - requires two sequential calls"""
        start_time = time.time()
        
        try:
            # Setup authentication
            auth = None
            
            # First try cookie authentication
            cookie_auth = self._get_cookie_auth()
            if cookie_auth:
                auth = cookie_auth
            # Fallback to username/password if provided
            elif self.config.auth and 'username' in self.config.auth and 'password' in self.config.auth:
                auth = aiohttp.BasicAuth(
                    login=self.config.auth['username'],
                    password=self.config.auth['password']
                )
            
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.config.timeout),
                auth=auth
            ) as session:
                headers = {'Content-Type': 'application/json'}
                if self.config.headers:
                    headers.update(self.config.headers)
                
                # Step 1: Get block hash for the given height
                block_hash_payload = {
                    "jsonrpc": "1.0",
                    "id": "get_block_hash",
                    "method": "getblockhash",
                    "params": [block_height]
                }
                
                self.logger.debug(f"Getting block hash for height {block_height}")
                
                async with session.post(
                    self.config.endpoint,
                    json=block_hash_payload,
                    headers=headers
                ) as response:
                    if response.status != 200:
                        error_msg = f"Failed to get block hash: HTTP {response.status}: {await response.text()}"
                        self.logger.error(error_msg)
                        return ServiceResult(
                            service_name=self.config.name,
                            block_height=block_height,
                            tweaks=[],
                            request_time=time.time() - start_time,
                            success=False,
                            error_message=error_msg
                        )
                    
                    hash_data = await response.json()
                    if 'error' in hash_data and hash_data['error']:
                        error_msg = f"RPC error getting block hash: {hash_data['error']}"
                        self.logger.error(error_msg)
                        return ServiceResult(
                            service_name=self.config.name,
                            block_height=block_height,
                            tweaks=[],
                            request_time=time.time() - start_time,
                            success=False,
                            error_message=error_msg
                        )
                    
                    block_hash = hash_data.get('result')
                    if not block_hash:
                        error_msg = f"No block hash returned for height {block_height}"
                        self.logger.error(error_msg)
                        return ServiceResult(
                            service_name=self.config.name,
                            block_height=block_height,
                            tweaks=[],
                            request_time=time.time() - start_time,
                            success=False,
                            error_message=error_msg
                        )
                
                # Step 2: Get silent payment data using the block hash
                # Use filter_spent and dust_limit from config if available, otherwise default
                filter_spent = self.config.filter_spent if self.config.filter_spent is not None else False
                dust_limit = self.config.dust_limit if self.config.dust_limit is not None else 0
                sp_data_payload = {
                    "jsonrpc": "1.0",
                    "id": "silent_payments_audit",
                    "method": "getsilentpaymentblockdata",
                    "params": [block_hash, dust_limit, filter_spent]
                }
                
                self.logger.debug(f"Getting silent payment data for block hash {block_hash}")
                
                async with session.post(
                    self.config.endpoint,
                    json=sp_data_payload,
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
            error_msg = f"Bitcoin Core RPC request error: {str(e)}"
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
        """Build Bitcoin Core specific RPC payload - not used in this implementation"""
        # This method is not used since we override get_tweaks_for_block
        # to handle the two-step process (getblockhash -> getsilentpaymentblockdata)
        return {
            "jsonrpc": "1.0",
            "id": "silent_payments_audit",
            "method": "getsilentpaymentblockdata",
            "params": [""]  # Block hash placeholder
        }
    
    def _normalize_response(self, raw_response: Any, block_height: int) -> List[TweakData]:
        """Normalize Bitcoin Core response format"""
        tweaks = []
        
        # Bitcoin Core returns the tweaks in the 'bip352_tweaks' field
        # Each tweak is a hex string representing the tweak hash
        if isinstance(raw_response, dict) and 'bip352_tweaks' in raw_response:
            bip352_tweaks = raw_response['bip352_tweaks']
            
            if isinstance(bip352_tweaks, list):
                for i, tweak_hash in enumerate(bip352_tweaks):
                    if isinstance(tweak_hash, str) and tweak_hash:
                        tweak = TweakData(
                            tweak_hash=tweak_hash,
                            block_height=block_height,
                            transaction_id='',  # Bitcoin Core doesn't provide txid in this response
                            output_index=i,     # Use array index as output index
                            raw_data={
                                'tweak': tweak_hash,
                                'index': i,
                                'source': 'bitcoin_core_bip352'
                            }
                        )
                        tweaks.append(tweak)
        
        return tweaks


class ElectrumServerService(HTTPIndexService):
    """Electrum server HTTP API implementation"""
    
    def _build_url(self, block_height: int) -> str:
        """Build Electrum server specific URL"""
        return f"{self.config.endpoint}/blockchain.block.header/{block_height}"
    
    def _normalize_response(self, raw_response: Any, block_height: int) -> List[TweakData]:
        """Normalize Electrum server response format"""
        tweaks = []
        
        # Electrum server example response processing
        # This would need to be customized based on actual Electrum API
        
        return tweaks


class ElectrsRPCService(SocketRPCIndexService):
    """Electrs/Esplora Cake socket RPC service implementation"""
    
    def _build_rpc_call(self, block_height: int) -> tuple:
        """Build Electrs specific RPC call"""
        dust_limit = self.config.dust_limit if self.config.dust_limit is not None else 0
        filter_spent = self.config.filter_spent if self.config.filter_spent is not None else False
        return 'blockchain.block.tweaks', [block_height, dust_limit, filter_spent]
    
    def _normalize_response(self, raw_response: Any, block_height: int) -> List[TweakData]:
        """Normalize Electrs response format"""
        tweaks = []
        
        # Electrs returns a list of tweak strings or objects
        if isinstance(raw_response, list):
            for i, tweak_data in enumerate(raw_response):
                if isinstance(tweak_data, str):
                    # Simple string response - just the tweak hash
                    tweak = TweakData(
                        tweak_hash=tweak_data,
                        block_height=block_height,
                        transaction_id='',  # Not provided in simple format
                        output_index=i,     # Use index as placeholder
                        raw_data={'tweak': tweak_data}
                    )
                    tweaks.append(tweak)
                elif isinstance(tweak_data, dict):
                    # More detailed response format
                    tweak = TweakData(
                        tweak_hash=tweak_data.get('tweak', tweak_data.get('hash', '')),
                        block_height=block_height,
                        transaction_id=tweak_data.get('txid', tweak_data.get('transaction_id', '')),
                        output_index=tweak_data.get('vout', tweak_data.get('output_index', i)),
                        raw_data=tweak_data
                    )
                    tweaks.append(tweak)
        
        return tweaks


class TweakIndexHTTPService(HTTPIndexService):
    """HTTP Tweak Index service implementation"""
    
    def _build_url(self, block_height: int) -> str:
        """Build URL for the tweak index endpoint"""
        base_endpoint = self.config.endpoint.rstrip('/')
        base_url = f"{base_endpoint}/{block_height}"

        # Add dust_limit as query parameter if configured
        if hasattr(self.config, 'dust_limit') and self.config.dust_limit is not None:
            separator = '&' if '?' in base_url else '?'
            base_url += f"{separator}dust_limit={self.config.dust_limit}"
        return base_url
    
    def _normalize_response(self, raw_response: Any, block_height: int) -> List[TweakData]:
        """Normalize tweak index HTTP response format"""
        tweaks = []
        
        # Handle different possible response formats
        
        # Format 1: Direct array of tweaks
        if isinstance(raw_response, list):
            for i, tweak_item in enumerate(raw_response):
                if isinstance(tweak_item, str):
                    # Simple string response - just the tweak hash
                    tweak = TweakData(
                        tweak_hash=tweak_item,
                        block_height=block_height,
                        transaction_id='',
                        output_index=i,
                        raw_data={'tweak': tweak_item, 'index': i}
                    )
                    tweaks.append(tweak)
                elif isinstance(tweak_item, dict):
                    # Object with more details
                    tweak = TweakData(
                        tweak_hash=tweak_item.get('tweak', tweak_item.get('hash', '')),
                        block_height=block_height,
                        transaction_id=tweak_item.get('txid', tweak_item.get('transaction_id', '')),
                        output_index=tweak_item.get('vout', tweak_item.get('output_index', i)),
                        raw_data=tweak_item
                    )
                    tweaks.append(tweak)
        
        # Format 2: Object with tweaks array
        elif isinstance(raw_response, dict):
            # Check various possible field names for the tweaks array
            tweaks_array = (raw_response.get('tweaks') or 
                          raw_response.get('silent_payment_tweaks') or
                          raw_response.get('data') or
                          raw_response.get('results') or
                          [])
            
            if isinstance(tweaks_array, list):
                for i, tweak_item in enumerate(tweaks_array):
                    if isinstance(tweak_item, str):
                        tweak = TweakData(
                            tweak_hash=tweak_item,
                            block_height=block_height,
                            transaction_id='',
                            output_index=i,
                            raw_data={'tweak': tweak_item, 'index': i}
                        )
                        tweaks.append(tweak)
                    elif isinstance(tweak_item, dict):
                        tweak = TweakData(
                            tweak_hash=tweak_item.get('tweak', tweak_item.get('hash', '')),
                            block_height=block_height,
                            transaction_id=tweak_item.get('txid', tweak_item.get('transaction_id', '')),
                            output_index=tweak_item.get('vout', tweak_item.get('output_index', i)),
                            raw_data=tweak_item
                        )
                        tweaks.append(tweak)
            
            # Handle case where the response itself contains metadata
            elif 'block_height' in raw_response:
                # Single tweak response or metadata format
                if 'tweak' in raw_response or 'hash' in raw_response:
                    tweak = TweakData(
                        tweak_hash=raw_response.get('tweak', raw_response.get('hash', '')),
                        block_height=block_height,
                        transaction_id=raw_response.get('txid', ''),
                        output_index=raw_response.get('vout', 0),
                        raw_data=raw_response
                    )
                    tweaks.append(tweak)
        
        return tweaks


class BlindBitGRPCService(GRPCIndexService):
    """BlindBit Oracle gRPC service implementation"""
    
    def __init__(self, config: ServiceConfig):
        super().__init__(config)
        
        # Import protobuf classes
        try:
            import grpc
            from pb.oracle_service_pb2_grpc import OracleServiceStub
            from pb.indexing_server_pb2 import BlockHeightRequest, GetTweakIndexRequest, RangedBlockHeightRequest
            self.grpc = grpc
            self.OracleServiceStub = OracleServiceStub
            self.BlockHeightRequest = BlockHeightRequest
            self.GetTweakIndexRequest = GetTweakIndexRequest
            self.RangedBlockHeightRequest = RangedBlockHeightRequest
        except ImportError as e:
            raise ImportError(f"Failed to import gRPC dependencies: {e}. Make sure grpcio and protobuf are installed.")
    
    async def get_tweaks_for_block(self, block_height: int) -> ServiceResult:
        """Get tweaks via BlindBit Oracle gRPC"""
        start_time = time.time()
        
        try:
            # Get gRPC channel and create stub
            channel = self._get_channel()
            stub = self.OracleServiceStub(channel)
            
            filter_spent = self.config.filter_spent if self.config.filter_spent is not None else False
            dust_limit = self.config.dust_limit if self.config.dust_limit is not None else 0
            # Determine which method to use based on filter_spent configuration
            if filter_spent:
                # Use GetTweakIndexArray with dust limit
                request = self.GetTweakIndexRequest(
                    block_height=block_height,
                    dust_limit=dust_limit
                )
                self.logger.debug(f"Making gRPC GetTweakIndexArray request for block {block_height} with dust_limit={dust_limit}")
                response = stub.GetTweakIndexArray(request, timeout=self.config.timeout)
            else:
                # Use basic GetTweakArray
                request = self.BlockHeightRequest(
                    block_height=block_height
                )
                self.logger.debug(f"Making gRPC GetTweakArray request for block {block_height}")
                response = stub.GetTweakArray(request, timeout=self.config.timeout)
            
            # Normalize the response
            tweaks = self._normalize_response(response, block_height)
            
            return ServiceResult(
                service_name=self.config.name,
                block_height=block_height,
                tweaks=tweaks,
                request_time=time.time() - start_time,
                success=True
            )
            
        except Exception as e:
            error_msg = f"BlindBit gRPC request error: {str(e)}"
            self.logger.error(error_msg)
            
            return ServiceResult(
                service_name=self.config.name,
                block_height=block_height,
                tweaks=[],
                request_time=time.time() - start_time,
                success=False,
                error_message=error_msg
            )
        finally:
            # Note: We keep the channel open for reuse, it will be closed when the service is destroyed
            pass
    
    async def get_tweaks_for_range_stream(self, start_block: int, end_block: int) -> List[ServiceResult]:
        """Get tweaks for a range of blocks using StreamBlockBatchSlim streaming"""
        start_time = time.time()
        results = []
        
        try:
            # Get gRPC channel and create stub
            channel = self._get_channel()
            stub = self.OracleServiceStub(channel)
            
            # Create ranged request
            request = self.RangedBlockHeightRequest(
                start=start_block,
                end=end_block
            )
            
            self.logger.debug(f"Making gRPC StreamBlockBatchSlim request for blocks {start_block}-{end_block}")
            
            # Start streaming
            stream = stub.StreamBlockBatchSlim(request, timeout=self.config.timeout)
            
            try:
                for batch in stream:
                    # Extract block height from the batch
                    block_height = batch.block_identifier.block_height
                    
                    # Normalize the batch response for this block
                    tweaks = self._normalize_stream_response(batch, block_height)
                    
                    # Create ServiceResult for this block
                    result = ServiceResult(
                        service_name=self.config.name,
                        block_height=block_height,
                        tweaks=tweaks,
                        request_time=time.time() - start_time,  # Will be updated at the end
                        success=True
                    )
                    results.append(result)
                    
                    self.logger.debug(f"Processed block {block_height} from stream: {len(tweaks)} tweaks")
            
            except Exception as stream_error:
                error_msg = f"Stream processing error: {str(stream_error)}"
                self.logger.error(f"BlindBit stream processing failed: {error_msg}, aborting range audit")
                
                # Return empty results list to indicate stream failure
                return []
            
            # Update timing for all results
            total_time = time.time() - start_time
            for result in results:
                result.request_time = total_time / len(results) if results else 0.0
            
            self.logger.info(f"Completed StreamBlockBatchSlim for {len(results)} blocks in {total_time:.2f}s")
            return results
            
        except Exception as e:
            error_msg = f"BlindBit streaming request error: {str(e)}"
            self.logger.error(f"{error_msg}, aborting range audit")
            return []
        finally:
            # Note: We keep the channel open for reuse, it will be closed when the service is destroyed
            pass
    
    def _normalize_response(self, raw_response: Any, block_height: int) -> List[TweakData]:
        """Normalize BlindBit gRPC response format"""
        tweaks = []
        
        # BlindBit Oracle returns a TweakArray with block_identifier and tweaks
        if hasattr(raw_response, 'tweaks'):
            for i, tweak_bytes in enumerate(raw_response.tweaks):
                # Convert bytes to hex string
                tweak_hash = tweak_bytes.hex() if isinstance(tweak_bytes, bytes) else str(tweak_bytes)
                
                tweak = TweakData(
                    tweak_hash=tweak_hash,
                    block_height=block_height,
                    transaction_id='',  # Not provided in BlindBit Oracle response
                    output_index=i,     # Use array index as output index
                    raw_data={
                        'tweak_bytes': tweak_bytes,
                        'index': i,
                        'source': 'blindbit_grpc_oracle'
                    }
                )
                tweaks.append(tweak)
        
        return tweaks
    
    def _normalize_stream_response(self, batch_response: Any, block_height: int) -> List[TweakData]:
        """Normalize BlindBit gRPC BlockBatchSlim stream response format"""
        tweaks = []
        
        # BlockBatchSlim contains: block_identifier, tweaks, new_utxos_filter, spent_utxos_filter
        if hasattr(batch_response, 'tweaks'):
            for i, tweak_bytes in enumerate(batch_response.tweaks):
                # Convert bytes to hex string
                tweak_hash = tweak_bytes.hex() if isinstance(tweak_bytes, bytes) else str(tweak_bytes)
                
                tweak = TweakData(
                    tweak_hash=tweak_hash,
                    block_height=block_height,
                    transaction_id='',  # Not provided in BlockBatchSlim
                    output_index=i,     # Use array index as output index
                    raw_data={
                        'tweak_bytes': tweak_bytes,
                        'index': i,
                        'source': 'blindbit_grpc_stream',
                        'block_hash': batch_response.block_identifier.block_hash.hex() if hasattr(batch_response.block_identifier, 'block_hash') else ''
                    }
                )
                tweaks.append(tweak)
        
        return tweaks
    
    def __del__(self):
        """Cleanup when service is destroyed"""
        self._close_channel()


class TestDataIndexService(IndexServiceInterface):
    """Test data service implementation that reads from stored canonical test data files"""
    
    def __init__(self, config: ServiceConfig, ignore_filter_mismatch: bool = False):
        super().__init__(config)
        if config.service_type != ServiceType.TEST_DATA:
            raise ValueError(f"TestDataIndexService requires TEST_DATA service type, got {config.service_type}")
        self.ignore_filter_mismatch = ignore_filter_mismatch
    
    async def get_tweaks_for_block(self, block_height: int) -> ServiceResult:
        """Get tweaks by reading from canonical test data file"""
        start_time = time.time()
        
        try:
            # Build path to test data file
            test_data_dir = Path("test_data")
            filename = f"block_{block_height}.json"
            filepath = test_data_dir / filename
            
            # Check if file exists
            if not filepath.exists():
                error_msg = f"Test data file not found: {filepath}"
                self.logger.error(error_msg)
                return ServiceResult(
                    service_name=self.config.name,
                    block_height=block_height,
                    tweaks=[],
                    request_time=time.time() - start_time,
                    success=False,
                    error_message=error_msg
                )
            
            # Read and parse canonical test data file
            with open(filepath, 'r') as f:
                test_data = json.load(f)
            
            # Validate test data format
            if 'tweaks' not in test_data:
                error_msg = f"Invalid test data format in {filepath}: missing 'tweaks' field"
                self.logger.error(error_msg)
                return ServiceResult(
                    service_name=self.config.name,
                    block_height=block_height,
                    tweaks=[],
                    request_time=time.time() - start_time,
                    success=False,
                    error_message=error_msg
                )
            
            # Log which reference service was used to create this test data
            reference_service = test_data.get('reference_service', 'unknown')
            self.logger.debug(f"Using canonical test data (originally from {reference_service})")
            
            # Skip filter validation for test_data services - they ARE the reference data
            # No need to validate the reference against itself
            
            # Normalize the canonical test data to TweakData objects
            tweaks = self._normalize_response(test_data, block_height)
            
            return ServiceResult(
                service_name=self.config.name,
                block_height=block_height,
                tweaks=tweaks,
                request_time=time.time() - start_time,
                success=True
            )
        
        except Exception as e:
            error_msg = f"Test data service error: {str(e)}"
            self.logger.error(error_msg)
            return ServiceResult(
                service_name=self.config.name,
                block_height=block_height,
                tweaks=[],
                request_time=time.time() - start_time,
                success=False,
                error_message=error_msg
            )
    
    def _normalize_response(self, raw_response: Any, block_height: int) -> List[TweakData]:
        """Normalize canonical test data format"""
        tweaks = []
        
        # Canonical test data format has 'tweaks' array with full tweak information
        if isinstance(raw_response, dict) and 'tweaks' in raw_response:
            for tweak_data in raw_response['tweaks']:
                if isinstance(tweak_data, dict):
                    tweak = TweakData(
                        tweak_hash=tweak_data.get('tweak_hash', ''),
                        block_height=tweak_data.get('block_height', block_height),
                        transaction_id=tweak_data.get('transaction_id', ''),
                        output_index=tweak_data.get('output_index', 0),
                        raw_data=tweak_data.get('raw_data', tweak_data)
                    )
                    tweaks.append(tweak)
        
        return tweaks
    
    def _validate_filter_config(self, reference_filter_config: dict, reference_service: str):
        """Validate that this service's filter config matches the reference test data"""
        if not reference_filter_config:
            # No reference filter config stored, can't validate
            return
        
        # Compare dust_limit
        ref_dust_limit = reference_filter_config.get('dust_limit')
        current_dust_limit = self.config.dust_limit
        
        # Compare filter_spent  
        ref_filter_spent = reference_filter_config.get('filter_spent')
        current_filter_spent = self.config.filter_spent
        
        mismatches = []
        
        # Check dust_limit mismatch
        if ref_dust_limit != current_dust_limit:
            mismatches.append(f"dust_limit: reference={ref_dust_limit}, current={current_dust_limit}")
        
        # Check filter_spent mismatch
        if ref_filter_spent != current_filter_spent:
            mismatches.append(f"filter_spent: reference={ref_filter_spent}, current={current_filter_spent}")
        
        if mismatches:
            # Format mismatches more clearly
            mismatch_parts = []
            if ref_dust_limit != current_dust_limit:
                mismatch_parts.append(f"dust_limit={current_dust_limit} (expected {ref_dust_limit})")
            if ref_filter_spent != current_filter_spent:
                mismatch_parts.append(f"filter_spent={current_filter_spent} (expected {ref_filter_spent})")
            
            mismatch_details = ", ".join(mismatch_parts)
            warning_msg = f"Service '{self.config.name}' filter mismatch with test data (from '{reference_service}'): {mismatch_details}"
            
            if self.ignore_filter_mismatch:
                self.logger.info(f"IGNORED: {warning_msg}")
            else:
                self.logger.warning(warning_msg)
                print(f"WARNING: {warning_msg}")
                print("         Use --ignore-filter-mismatch to suppress this warning.")


# Factory function to create service instances
def create_service_instance(config: ServiceConfig, ignore_filter_mismatch: bool = False) -> Union[HTTPIndexService, RPCIndexService, SocketRPCIndexService, GRPCIndexService, TestDataIndexService]:
    """
    Factory function to create appropriate service instance based on config
    
    Args:
        config: ServiceConfig with service-specific details
        ignore_filter_mismatch: Whether to ignore filter config mismatches
        
    Returns:
        Appropriate service instance
    """
    service_name_lower = config.name.lower()
    
    if config.service_type == ServiceType.HTTP:
        if 'electrum' in service_name_lower:
            return ElectrumServerService(config) # TODO
        elif 'blindbit' in service_name_lower:
            return TweakIndexHTTPService(config)
        else:
            return ExampleHTTPService(config)
    
    elif config.service_type == ServiceType.RPC:
        if 'bitcoin' in service_name_lower:
            return BitcoinCoreRPCService(config)
        else:
            return ExampleRPCService(config)
    
    elif config.service_type == ServiceType.SOCKET_RPC:
        if 'esplora' in service_name_lower or 'electrs' in service_name_lower:
            return ElectrsRPCService(config)
        else:
            return SocketRPCIndexService(config)
    
    elif config.service_type == ServiceType.GRPC:
        if 'blindbit' in service_name_lower:
            return BlindBitGRPCService(config)
    
    elif config.service_type == ServiceType.TEST_DATA:
        return TestDataIndexService(config, ignore_filter_mismatch)

    raise ValueError(f"Unsupported service type: {config.service_type}")
