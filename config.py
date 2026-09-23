"""
Configuration management for Silent Payments Tweak Service Auditor
"""
import json
import os
import re
from pathlib import Path
from typing import List, Optional, Any, Dict
from models import ServiceConfig, ServiceType, ServicePair

# Canonical environment variable mappings for automatic discovery and overrides
ENV_SERVICE_MAPPINGS: Dict[str, Dict[str, Any]] = {
    "RBITCOIN_ENDPOINT": {
        "service_name": "rbitcoin",
        "service_type": ServiceType.SOCKET_RPC,
        "default_timeout": 30,
    },
    "BLINDBIT_GRPC_ENDPOINT": {
        "service_name": "blindbit-grpc",
        "service_type": ServiceType.GRPC,
        "default_timeout": 60,
        "requests_per_second": 150,
        "dust_limit": 0,
    },
    "BLINDBIT_HTTP_ENDPOINT": {
        "service_name": "blindbit",
        "service_type": ServiceType.HTTP,
        "default_timeout": 30,
        "headers": {"User-Agent": "TweakServiceAuditor/1.0"},
        "requests_per_second": 100,
    },
    "ESPLORA_ENDPOINT": {
        "service_name": "esplora-cake",
        "service_type": ServiceType.SOCKET_RPC,
        "default_timeout": 30,
    },
    "ELECTRS_ENDPOINT": {
        "service_name": "electrs",
        "service_type": ServiceType.SOCKET_RPC,
        "default_timeout": 30,
    },
    "BITCOIN_RPC_ENDPOINT": {
        "service_name": "bitcoin",
        "service_type": ServiceType.RPC,
        "default_timeout": 60,
        "headers": {"User-Agent": "TweakServiceAuditor/1.0"},
    },
}

# Service name to environment variable override mappings
SERVICE_ENV_VAR_MAPPINGS: Dict[str, str] = {
    "rbitcoin": "RBITCOIN_ENDPOINT",
    "rbitcoin-node": "RBITCOIN_ENDPOINT",
    "rbitcoin-signet": "RBITCOIN_ENDPOINT",
    "blindbit-grpc": "BLINDBIT_GRPC_ENDPOINT",
    "blindbit": "BLINDBIT_HTTP_ENDPOINT",
    "blindbit-oracle": "BLINDBIT_HTTP_ENDPOINT",
    "esplora-cake": "ESPLORA_ENDPOINT",
    "electrs": "ELECTRS_ENDPOINT",
    "bitcoin": "BITCOIN_RPC_ENDPOINT",
    "bitcoind": "BITCOIN_RPC_ENDPOINT",
}


def expand_env_vars(val: Any) -> Any:
    """Recursively expands ${VAR:-default}, ${VAR}, and $VAR in strings and collections."""
    if isinstance(val, str):
        def replace_match(match):
            var_name = match.group(1) or match.group(3)
            default_val = match.group(2) if match.group(2) is not None else ""
            return os.environ.get(var_name, default_val)

        pattern = re.compile(r'\$\{([A-Za-z0-9_]+)(?::-([^}]*))?\}|\$([A-Za-z0-9_]+)')
        return pattern.sub(replace_match, val)
    elif isinstance(val, dict):
        return {k: expand_env_vars(v) for k, v in val.items()}
    elif isinstance(val, list):
        return [expand_env_vars(item) for item in val]
    return val


class ConfigManager:
    """Manages configuration for the auditor with 3-tier hierarchy:
    Tier 1: Dynamic environment variable override (e.g. RBITCOIN_ENDPOINT overrides JSON endpoint)
    Tier 2: Environment variable expansion in JSON (${VAR:-default})
    Tier 3: Pure environment auto-discovery if config file does not exist
    """
    
    def __init__(self, config_file: Optional[str] = None):
        """
        Initialize configuration manager
        
        Args:
            config_file: Path to configuration file. If None, looks for config.json
        """
        self.config_file = config_file or "config.json"
        self.services: List[ServiceConfig] = []
        self.service_pairs: List[ServicePair] = []
        
        if os.path.exists(self.config_file):
            self.load_config()
        else:
            self.load_from_environment()

    def load_from_environment(self) -> None:
        """Tier 3: Auto-discover services and comparison pairs from environment variables"""
        self.services = []
        self.service_pairs = []

        for env_var, meta in ENV_SERVICE_MAPPINGS.items():
            endpoint_val = os.getenv(env_var)
            if endpoint_val:
                service_config = ServiceConfig(
                    name=meta["service_name"],
                    service_type=meta["service_type"],
                    endpoint=endpoint_val,
                    timeout=meta.get("default_timeout", 30),
                    headers=meta.get("headers"),
                    requests_per_second=meta.get("requests_per_second", 200),
                    dust_limit=meta.get("dust_limit"),
                    active=True
                )
                self.services.append(service_config)

        # If 2 or more active services were auto-discovered, automatically create pairs
        active_names = [s.name for s in self.services if s.active]
        if len(active_names) >= 2:
            for i in range(len(active_names)):
                for j in range(i + 1, len(active_names)):
                    name1, name2 = active_names[i], active_names[j]
                    self.service_pairs.append(
                        ServicePair(
                            name=f"{name1}-vs-{name2}",
                            service1=name1,
                            service2=name2,
                            active=True
                        )
                    )

        # Auto-create test_data services if test_data files exist
        self._auto_create_test_data_services()
    
    def load_config(self) -> None:
        """Load configuration from file applying Tier 1 and Tier 2 resolution"""
        try:
            with open(self.config_file, 'r') as f:
                raw_config_data = json.load(f)

            # Tier 2: Expand environment variables in JSON structure
            config_data = expand_env_vars(raw_config_data)
            
            # Load services
            self.services = []
            for service_data in config_data.get('services', []):
                service_name = service_data['name']
                endpoint = service_data.get('endpoint', '')
                active = service_data.get('active', True)

                # Tier 1: Dynamic override if specific environment variable is set
                env_var = SERVICE_ENV_VAR_MAPPINGS.get(service_name.lower())
                if env_var and os.getenv(env_var):
                    endpoint = os.getenv(env_var)
                    active = True

                service_config = ServiceConfig(
                    name=service_name,
                    service_type=ServiceType(service_data.get('service_type', None)),
                    endpoint=endpoint,
                    auth=service_data.get('auth'),
                    headers=service_data.get('headers'),
                    timeout=service_data.get('timeout', 60),
                    host=service_data.get('host'),
                    port=service_data.get('port'),
                    cookie_file=service_data.get('cookie_file'),
                    active=active,
                    requests_per_second=service_data.get('requests_per_second', 200),
                    filter_spent=service_data.get('filter_spent'),
                    dust_limit=service_data.get('dust_limit')
                )
                self.services.append(service_config)
            
            # Load service pairs
            self.service_pairs = []
            for pair_data in config_data.get('service_pairs', []):
                service_pair = ServicePair(
                    name=pair_data['name'],
                    service1=pair_data['service1'],
                    service2=pair_data['service2'],
                    active=pair_data.get('active', True)
                )
                self.service_pairs.append(service_pair)
            
            # Auto-create test_data services from service_pairs if they don't exist
            self._auto_create_test_data_services()
                
        except Exception as e:
            raise ValueError(f"Failed to load config from {self.config_file}: {e}")

    def _auto_create_test_data_services(self):
        """Auto-create test_data services for service_pairs references that don't exist"""
        if not self.service_pairs:
            return
            
        # Get existing service names and active service names
        existing_service_names = {service.name for service in self.services}
        
        # Find services referenced in pairs that don't exist
        missing_services = set()
        for pair in self.service_pairs:
            if pair.active:
                if pair.service1 not in existing_service_names:
                    missing_services.add(pair.service1)
                if pair.service2 not in existing_service_names:
                    missing_services.add(pair.service2)
        
        # Check if test_data directory exists
        test_data_dir = Path("test_data")
        if not test_data_dir.exists():
            return  # No test data available
        
        # Auto-create test_data services for missing services that have test data
        for missing_service in missing_services:
            # Check if any test data files exist that could be used by this service
            test_files = list(test_data_dir.glob("block_*.json"))
            if test_files:
                # Create a test_data service
                auto_service = ServiceConfig(
                    name="test_data",
                    service_type=ServiceType.TEST_DATA,
                    endpoint="local",
                    active=True
                )
                self.services.append(auto_service)

    def validate_config(self) -> List[str]:
        """Validate current configuration and return list of issues"""
        issues = []
        
        if not self.services:
            issues.append("No services configured")
            return issues
        
        service_names = []
        for i, service in enumerate(self.services):
            # Check for required fields
            if not service.name:
                issues.append(f"Service {i}: Missing name")
            elif service.name in service_names:
                issues.append(f"Service {i}: Duplicate name '{service.name}'")
            else:
                service_names.append(service.name)
            
            if not service.service_type.value:
                issues.append(f"Service '{service.name}': Missing service_type")

            # Endpoint is optional for test_data services (specifies which service data to read)
            if not service.endpoint and service.service_type != ServiceType.TEST_DATA:
                issues.append(f"Service '{service.name}': Missing endpoint")
            
        # Validate service pairs
        pair_names = []
        for i, pair in enumerate(self.service_pairs):
            if not pair.active:
                continue
            if not pair.name:
                issues.append(f"Service pair {i}: Missing name")
            elif pair.name in pair_names:
                issues.append(f"Service pair {i}: Duplicate name '{pair.name}'")
            else:
                pair_names.append(pair.name)
            
            if pair.service1 not in service_names:
                issues.append(f"Service pair '{pair.name}': service1 '{pair.service1}' not found in services")
            
            if pair.service2 not in service_names:
                issues.append(f"Service pair '{pair.name}': service2 '{pair.service2}' not found in services")
            
            if pair.service1 == pair.service2:
                issues.append(f"Service pair '{pair.name}': service1 and service2 cannot be the same")
        
        return issues
    
    def print_services(self):
        """Print all configured services with their status (active/inactive)"""
        print("Configured services:")
        for service in self.services:
            status = "" if service.active else " - inactive"
            print(f"  {service.name} ({service.service_type.value}): {service.endpoint}{status}")
        
        if self.service_pairs:
            print(f"\nConfigured service pairs:")
            for pair in self.service_pairs:
                status = "" if pair.active else " - inactive"
                print(f"  {pair.name}: {pair.service1} vs {pair.service2}{status}")
    
    def get_active_service_pairs(self) -> List[ServicePair]:
        """Get list of active service pairs"""
        return [pair for pair in self.service_pairs if pair.active]
