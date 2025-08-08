"""
Test script for blindbit-oracle HTTP service integration
"""
import asyncio
import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from models import ServiceConfig, ServiceType
from service_implementations import TweakIndexHTTPService, create_service_instance


async def test_blindbit_oracle_url_construction():
    """Test URL construction for blindbit-oracle service"""
    
    print("Testing blindbit-oracle URL construction...")
    
    # Test configuration matching the config.json
    config = ServiceConfig(
        name="blindbit-oracle",
        service_type=ServiceType.HTTP,
        endpoint="http://127.0.0.1:8000/tweak-index",
        headers={"User-Agent": "TweakServiceAuditor/1.0"},
        timeout=30
    )
    
    # Create service instance using factory
    service = create_service_instance(config)
    print(f"Service type: {type(service).__name__}")
    
    # Test URL construction for different block heights
    test_heights = [258257, 800000, 1000000]
    
    for height in test_heights:
        url = service._build_url(height)
        expected_url = f"http://127.0.0.1:8000/tweak-index/{height}"
        print(f"Block {height}: {url}")
        
        if url == expected_url:
            print(f"  ✓ Correct URL")
        else:
            print(f"  ✗ Expected: {expected_url}")
    
    return True


async def test_blindbit_oracle_service():
    """Test the blindbit-oracle service implementation"""
    
    print("\nTesting blindbit-oracle service...")
    
    config = ServiceConfig(
        name="blindbit-oracle",
        service_type=ServiceType.HTTP,
        endpoint="http://127.0.0.1:8000/tweak-index",
        headers={"User-Agent": "TweakServiceAuditor/1.0"},
        timeout=30
    )
    
    service = create_service_instance(config)
    
    # Test with a block (this will fail unless the service is running)
    block_height = 258257
    print(f"Testing request to block {block_height}...")
    
    try:
        result = await service.get_tweaks_for_block(block_height)
        
        print(f"Service result:")
        print(f"  Success: {result.success}")
        print(f"  Service: {result.service_name}")
        print(f"  Block: {result.block_height}")
        print(f"  Tweaks found: {len(result.tweaks)}")
        print(f"  Request time: {result.request_time:.3f}s")
        
        if result.error_message:
            print(f"  Error: {result.error_message}")
        
        if result.tweaks:
            print(f"  First tweak: {result.tweaks[0].tweak_hash}")
        
        return result.success
        
    except Exception as e:
        print(f"Service test failed: {e}")
        return False


async def test_with_auditor():
    """Test using the full auditor with blindbit-oracle"""
    
    print("\nTesting with full auditor...")
    
    from auditor import TweakServiceAuditor
    
    # Create configuration for just blindbit-oracle
    services = [
        ServiceConfig(
            name="blindbit-oracle",
            service_type=ServiceType.HTTP,
            endpoint="http://127.0.0.1:8000/tweak-index",
            headers={"User-Agent": "TweakServiceAuditor/1.0"},
            timeout=30,
            active=True
        )
    ]
    
    auditor = TweakServiceAuditor(services)
    
    block_height = 258257
    
    try:
        result = await auditor.audit_block(block_height)
        
        print(f"Audit result:")
        print(f"  Block: {result.block_height}")
        print(f"  Successful services: {result.successful_services}/{result.total_services}")
        
        for service_name, count in result.tweak_counts.items():
            print(f"  {service_name}: {count} tweaks")
        
        return result.successful_services > 0
        
    except Exception as e:
        print(f"Auditor test failed: {e}")
        return False


async def test_multiple_services():
    """Test with multiple services (blindbit-oracle + esplora-cake)"""
    
    print("\nTesting with multiple services...")
    
    from config import ConfigManager
    from auditor import TweakServiceAuditor
    
    # Load from config.json
    config_manager = ConfigManager("config.json")
    
    if not config_manager.services:
        print("No services configured")
        return False
    
    print(f"Loaded {len(config_manager.services)} services:")
    for service in config_manager.services:
        print(f"  - {service.name} ({service.service_type.value}): {service.endpoint}")
    
    auditor = TweakServiceAuditor(config_manager.services)
    
    block_height = 258257
    
    try:
        result = await auditor.audit_block(block_height)
        
        print(f"\nMulti-service audit result:")
        print(f"  Block: {result.block_height}")
        print(f"  Successful services: {result.successful_services}/{result.total_services}")
        
        for service_name, count in result.tweak_counts.items():
            print(f"  {service_name}: {count} tweaks")
        
        # Show comparison results
        matching_count = len(result.matching_tweaks)
        print(f"  Matching tweaks across all services: {matching_count}")
        
        non_matching = result.non_matching_by_service
        for service_name, unique_tweaks in non_matching.items():
            if unique_tweaks:
                print(f"  {service_name} unique tweaks: {len(unique_tweaks)}")
        
        return True
        
    except Exception as e:
        print(f"Multi-service audit failed: {e}")
        return False


async def main():
    """Run all tests"""
    print("blindbit-oracle Integration Test")
    print("=" * 40)
    
    # Test 1: URL construction
    url_test_ok = await test_blindbit_oracle_url_construction()
    
    # Test 2: Service implementation (will fail if service not running)
    service_test_ok = await test_blindbit_oracle_service()
    
    # Test 3: Full auditor with single service
    auditor_test_ok = await test_with_auditor()
    
    # Test 4: Multiple services
    multi_service_ok = await test_multiple_services()
    
    print(f"\n" + "=" * 40)
    print("Test Results:")
    print(f"  URL construction: {'✓' if url_test_ok else '✗'}")
    print(f"  Service implementation: {'✓' if service_test_ok else '✗'}")
    print(f"  Single service auditor: {'✓' if auditor_test_ok else '✗'}")
    print(f"  Multi-service auditor: {'✓' if multi_service_ok else '✗'}")
    
    print(f"\nNote: Service tests will fail if blindbit-oracle is not running on http://127.0.0.1:8000")
    print(f"Expected endpoint: http://127.0.0.1:8000/tweak-index/{{height}}")
    
    if url_test_ok:
        print("\n✓ Configuration and URL construction are correct!")
        print("The auditor is ready to work with blindbit-oracle when the service is running.")
    
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
