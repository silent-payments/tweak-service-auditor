"""
Test script for Esplora Cake socket RPC integration
"""
import asyncio
import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from socket_client import AsyncConnection
from models import ServiceConfig, ServiceType
from service_implementations import ElectrsRPCService


async def test_esplora_cake_connection():
    """Test the basic socket connection to Esplora Cake"""
    
    # Default Esplora Cake configuration
    host = '127.0.0.1'
    port = 60601
    
    print(f"Testing socket connection to {host}:{port}")
    
    try:
        async with AsyncConnection((host, port)) as conn:
            # Test basic connection with a simple call
            response = await conn.call('blockchain.block.tweaks', 258257)
            print(f"Raw response: {response}")
            
            if 'result' in response:
                result = response['result']
                print(f"Number of tweaks found: {len(result) if isinstance(result, list) else 'N/A'}")
                
                if isinstance(result, list) and result:
                    print(f"First few tweaks: {result[:3]}")
                
                return True
            else:
                print(f"Unexpected response format: {response}")
                return False
                
    except Exception as e:
        print(f"Connection failed: {e}")
        print("Make sure Esplora Cake is running on 127.0.0.1:60601")
        return False


async def test_esplora_cake_service():
    """Test the EsploraCakeService implementation"""
    
    print("\nTesting EsploraCakeService implementation...")
    
    # Create service configuration
    config = ServiceConfig(
        name="test-esplora-cake",
        service_type=ServiceType.SOCKET_RPC,
        endpoint="127.0.0.1:60601",
        timeout=30,
        active=True
    )
    
    # Create service instance
    service = ElectrsRPCService(config)
    
    # Test with a block
    block_height = 258257
    print(f"Testing with block height: {block_height}")
    
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
    """Test using the full auditor with Esplora Cake"""
    
    print("\nTesting with full auditor...")
    
    from auditor import TweakServiceAuditor
    
    # Create configuration for just Esplora Cake
    services = [
        ServiceConfig(
            name="esplora-cake-test",
            service_type=ServiceType.SOCKET_RPC,
            endpoint="127.0.0.1:60601",
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


async def main():
    """Run all tests"""
    print("Esplora Cake Integration Test")
    print("=" * 40)
    
    # Test 1: Basic socket connection
    connection_ok = await test_esplora_cake_connection()
    
    if not connection_ok:
        print("\nSkipping further tests - connection failed")
        print("\nTo run Esplora Cake locally:")
        print("1. Make sure you have an Esplora Cake instance running")
        print("2. Default configuration is host=127.0.0.1, port=60601")
        print("3. The service should respond to 'blockchain.block.tweaks' method")
        return 1
    
    # Test 2: Service implementation
    service_ok = await test_esplora_cake_service()
    
    # Test 3: Full auditor
    auditor_ok = await test_with_auditor()
    
    print(f"\n" + "=" * 40)
    print("Test Results:")
    print(f"  Socket connection: {'✓' if connection_ok else '✗'}")
    print(f"  Service implementation: {'✓' if service_ok else '✗'}")
    print(f"  Full auditor: {'✓' if auditor_ok else '✗'}")
    
    if all([connection_ok, service_ok, auditor_ok]):
        print("\n✓ All tests passed! Esplora Cake integration is working.")
        return 0
    else:
        print("\n✗ Some tests failed. Check the output above for details.")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
