"""
Example implementations of specific indexing services
These demonstrate how to extend the base HTTP and RPC service classes
"""
import time
import aiohttp
import os
from typing import List, Dict, Any, Union
from service_interface import HTTPIndexService, RPCIndexService, SocketRPCIndexService
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
        return 'blockchain.block.tweaks', [block_height]
    
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


# Factory function to create service instances
def create_service_instance(config: ServiceConfig) -> Union[HTTPIndexService, RPCIndexService, SocketRPCIndexService]:
    """
    Factory function to create appropriate service instance based on config
    
    Args:
        config: ServiceConfig with service-specific details
        
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
        if 'esplora-cake' in service_name_lower or 'electrs' in service_name_lower:
            return ElectrsRPCService(config)
        else:
            return SocketRPCIndexService(config)
    
    else:
        raise ValueError(f"Unsupported service type: {config.service_type}")
