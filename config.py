"""
Configuration management for Silent Payments Tweak Service Auditor
"""
import json
import os
from typing import List, Optional
from models import ServiceConfig, ServiceType, ServicePair


class ConfigManager:
    """Manages configuration for the auditor"""
    
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
    
    def load_config(self) -> None:
        """Load configuration from file"""
        try:
            with open(self.config_file, 'r') as f:
                config_data = json.load(f)
            
            # Load services
            self.services = []
            for service_data in config_data.get('services', []):
                service_config = ServiceConfig(
                    name=service_data['name'],
                    service_type=ServiceType(service_data.get('service_type', None)),
                    endpoint=service_data['endpoint'],
                    auth=service_data.get('auth'),
                    headers=service_data.get('headers'),
                    timeout=service_data.get('timeout', 60),
                    host=service_data.get('host'),
                    port=service_data.get('port'),
                    cookie_file=service_data.get('cookie_file'),
                    active=service_data.get('active'),
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
                
        except Exception as e:
            raise ValueError(f"Failed to load config from {self.config_file}: {e}")

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

            if not service.endpoint:
                issues.append(f"Service '{service.name}': Missing endpoint")
            
        # Validate service pairs
        pair_names = []
        for i, pair in enumerate(self.service_pairs):
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
            print(f"  {service.name} ({service.service_type.value}): {service.endpoint} {status}")
        
        if self.service_pairs:
            print(f"\nConfigured service pairs:")
            for pair in self.service_pairs:
                status = "" if pair.active else " - inactive"
                print(f"  {pair.name}: {pair.service1} vs {pair.service2}{status}")
    
    def get_active_service_pairs(self) -> List[ServicePair]:
        """Get list of active service pairs"""
        return [pair for pair in self.service_pairs if pair.active]
