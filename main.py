"""
Command Line Interface for Silent Payments Tweak Service Auditor
"""
import argparse
import asyncio
import logging
import json
import sys
import os
from pathlib import Path
from typing import List

from auditor import TweakServiceAuditor
from config import ConfigManager
from models import AuditResult, RangeAuditResult, PairwiseComparison, ServiceConfig, ServiceType


def setup_logging(verbosity: int = 0):
    """Setup logging configuration based on verbosity level
    
    Args:
        verbosity: 0 = WARNING+ERROR only, 1 = INFO+, 2 = DEBUG+
    """
    if verbosity >= 2:
        level = logging.DEBUG
    elif verbosity >= 1:
        level = logging.INFO
    else:
        level = logging.WARNING
    
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )


def print_pairwise_comparisons(comparisons: List[PairwiseComparison], detailed: bool = False, service_configs: List[ServiceConfig] = None, ignore_filter_mismatch: bool = False):
    """Print pairwise comparison results in a readable format"""
    if not comparisons:
        return
    
    print(f"\n=== Pairwise Service Comparisons ===")
    
    for comparison in comparisons:
        # Check for filter mismatches between services
        if service_configs and not ignore_filter_mismatch:
            _check_comparison_filter_mismatch(comparison, service_configs)
        print(f"\n{comparison.pair_name} ({comparison.service1_name} vs {comparison.service2_name}):")
        print(f"  {comparison.service1_name}: {len(comparison.service1_tweaks)} tweaks")
        print(f"  {comparison.service2_name}: {len(comparison.service2_tweaks)} tweaks")
        print(f"  Matching tweaks: {len(comparison.matching_tweaks)}")
        print(f"  {comparison.service1_name} unique: {len(comparison.service1_unique)}")
        print(f"  {comparison.service2_name} unique: {len(comparison.service2_unique)}")
        print(f"  Match percentage: {comparison.match_percentage:.1f}%")
        
        if detailed:
            if comparison.service1_unique:
                print(f"    {comparison.service1_name} unique tweaks (first 5):")
                for tweak in list(comparison.service1_unique)[:5]:
                    print(f"      {tweak}")
                if len(comparison.service1_unique) > 5:
                    print(f"      ... and {len(comparison.service1_unique) - 5} more")
            
            if comparison.service2_unique:
                print(f"    {comparison.service2_name} unique tweaks (first 5):")
                for tweak in list(comparison.service2_unique)[:5]:
                    print(f"      {tweak}")
                if len(comparison.service2_unique) > 5:
                    print(f"      ... and {len(comparison.service2_unique) - 5} more")


def _check_comparison_filter_mismatch(comparison: PairwiseComparison, service_configs: List[ServiceConfig]):
    """Check for filter configuration mismatches between services in a comparison"""
    # Get configs for both services
    service1_config = next((c for c in service_configs if c.name == comparison.service1_name), None)
    service2_config = next((c for c in service_configs if c.name == comparison.service2_name), None)
    
    if not service1_config or not service2_config:
        return
    
    # Check if one service is test_data and the other is not
    service1_is_test = service1_config.service_type == ServiceType.TEST_DATA
    service2_is_test = service2_config.service_type == ServiceType.TEST_DATA
    
    # Only validate if exactly one service is test_data
    if service1_is_test == service2_is_test:
        return  # Both are test_data or both are real services
    
    # Determine which is the real service and which is test_data
    if service1_is_test:
        test_service = service1_config
        real_service = service2_config
        test_service_name = comparison.service1_name
        real_service_name = comparison.service2_name
    else:
        test_service = service2_config
        real_service = service1_config
        test_service_name = comparison.service2_name
        real_service_name = comparison.service1_name
    
    # We need to read the test data to get the reference filter config
    from pathlib import Path
    test_data_dir = Path("test_data")
    
    # We need the block height, but we don't have it here. We'll need to get it from somewhere.
    # For now, let's check if there are any test files and read the first one to get reference config
    test_files = list(test_data_dir.glob("block_*.json"))
    if not test_files:
        return
    
    try:
        import json
        with open(test_files[0], 'r') as f:
            test_data = json.load(f)
        
        reference_filter_config = test_data.get('reference_filter_config', {})
        if not reference_filter_config:
            return
        
        ref_dust_limit = reference_filter_config.get('dust_limit')
        ref_filter_spent = reference_filter_config.get('filter_spent')
        
        real_dust_limit = real_service.dust_limit
        real_filter_spent = real_service.filter_spent
        
        # Check for mismatches
        mismatches = []
        if ref_dust_limit != real_dust_limit:
            mismatches.append(f"dust_limit={real_dust_limit} (test data has {ref_dust_limit})")
        if ref_filter_spent != real_filter_spent:
            mismatches.append(f"filter_spent={real_filter_spent} (test data has {ref_filter_spent})")
        
        if mismatches:
            reference_service = test_data.get('reference_service', 'unknown')
            mismatch_details = ", ".join(mismatches)
            warning_msg = f"Service '{real_service_name}' has filter mismatch with test data (from '{reference_service}'): {mismatch_details}"
            print(f"WARNING: {warning_msg}")
            print("         This comparison may not be meaningful due to different filtering.")
    
    except Exception:
        # If we can't read test data, skip validation
        pass


def print_audit_result(result: AuditResult, detailed: bool = False, service_pairs: List = None, service_configs: List[ServiceConfig] = None, ignore_filter_mismatch: bool = False):
    print(f"\n=== Audit Results for Block {result.block_height} ===")
    print(f"Services: {result.successful_services}/{result.total_services} successful")
    
    # Print tweak counts per service
    print("\nTweak counts by service:")
    for service_name, count in result.tweak_counts.items():
        print(f"  {service_name}: {count} tweaks")
    
    # Print matching information
    matching_count = len(result.matching_tweaks)
    print(f"\nMatching tweaks across all services: {matching_count}")
    
    # Print unique tweaks per service
    non_matching = result.non_matching_by_service
    print("\nUnique tweaks by service:")
    for service_name, unique_tweaks in non_matching.items():
        print(f"  {service_name}: {len(unique_tweaks)} unique tweaks")
        if detailed and unique_tweaks:
            for tweak in list(unique_tweaks)[:5]:  # Show first 5
                print(f"    {tweak}")
            if len(unique_tweaks) > 5:
                print(f"    ... and {len(unique_tweaks) - 5} more")

    # Print total request time per service
    print("\nTotal request time by service:")
    for service_name, total_time in result.total_request_time_by_service.items():
        print(f"  {service_name}: {total_time:.3f} seconds")
    
    # Print failed services
    failed_services = [r for r in result.service_results if not r.success]
    if failed_services:
        print("\nFailed services:")
        for service_result in failed_services:
            print(f"  {service_result.service_name}: {service_result.error_message}")
    
    # Print pairwise comparisons if service pairs are configured
    if service_pairs:
        pairwise_comparisons = result.pairwise_comparisons(service_pairs)
        print_pairwise_comparisons(pairwise_comparisons, detailed, service_configs, ignore_filter_mismatch)


def store_test_data(result: AuditResult, service_configs: List[ServiceConfig], reference_service: str = None):
    """Store full tweak output for a block to test_data/ directory as canonical reference data"""
    test_data_dir = Path("test_data")
    test_data_dir.mkdir(exist_ok=True)
    
    # Create filename based on block height
    filename = f"block_{result.block_height}.json"
    filepath = test_data_dir / filename
    
    # Find the reference service to use as canonical data
    reference_result = None
    
    if reference_service:
        # Use specified service as reference
        reference_result = next((r for r in result.service_results if r.service_name == reference_service and r.success), None)
        if not reference_result:
            print(f"Warning: Specified reference service '{reference_service}' not found or failed. Using first successful service.")
    
    # If no specific service or it failed, use first successful service
    if not reference_result:
        reference_result = next((r for r in result.service_results if r.success), None)
    
    if not reference_result:
        print("Error: No successful services found. Cannot store test data.")
        return
    
    # Get the reference service config to store filter settings
    reference_config = None
    for config in service_configs:
        if config.name == reference_result.service_name:
            reference_config = config
            break
    
    # Prepare canonical test data 
    test_data = {
        "block_height": result.block_height,
        "reference_service": reference_result.service_name,
        "tweak_count": len(reference_result.tweaks),
        "reference_filter_config": {
            "dust_limit": reference_config.dust_limit if reference_config else None,
            "filter_spent": reference_config.filter_spent if reference_config else None
        },
        "tweaks": [
            {
                "tweak_hash": tweak.tweak_hash,
                "block_height": tweak.block_height,
                "transaction_id": tweak.transaction_id,
                "output_index": tweak.output_index,
                "raw_data": tweak.raw_data
            }
            for tweak in reference_result.tweaks
        ]
    }
    
    # Write test data to file
    with open(filepath, 'w') as f:
        json.dump(test_data, f, indent=2)
    
    print(f"Test data stored to {filepath} (reference: {reference_result.service_name}, {len(reference_result.tweaks)} tweaks)")


def print_range_result(result: RangeAuditResult, detailed: bool = False, service_pairs: List = None):
    """Print range audit result in a readable format"""
    print(f"\n=== Range Audit Results (Blocks {result.start_block}-{result.end_block}) ===")
    print(f"Total blocks processed: {result.total_blocks_audited}")
    
    # Print summary by service
    print("\nSummary by service:")
    summary = result.summary_by_service
    for service_name, stats in summary.items():
        print(f"  {service_name}:")
        print(f"    Total tweaks: {stats['total_tweaks']}")
        print(f"    Blocks processed: {stats['blocks_processed']}")
        print(f"    Failures: {stats['failures']}")

    # Print total request time per service
    print("\nTotal request time by service (all blocks):")
    for service_name, total_time in result.total_request_time_by_service.items():
        print(f"  {service_name}: {total_time:.3f} seconds")
    
    # Print pairwise comparison summary for the range
    if service_pairs and result.block_results:
        print(f"\n=== Pairwise Comparison Summary ===")
        
        # Aggregate pairwise stats across all blocks
        pair_stats = {}
        for block_result in result.block_results:
            pairwise_comparisons = block_result.pairwise_comparisons(service_pairs)
            for comparison in pairwise_comparisons:
                if comparison.pair_name not in pair_stats:
                    pair_stats[comparison.pair_name] = {
                        'total_blocks': 0,
                        'total_matching': 0,
                        'total_service1_unique': 0,
                        'total_service2_unique': 0,
                        'service1_name': comparison.service1_name,
                        'service2_name': comparison.service2_name
                    }
                
                pair_stats[comparison.pair_name]['total_blocks'] += 1
                pair_stats[comparison.pair_name]['total_matching'] += len(comparison.matching_tweaks)
                pair_stats[comparison.pair_name]['total_service1_unique'] += len(comparison.service1_unique)
                pair_stats[comparison.pair_name]['total_service2_unique'] += len(comparison.service2_unique)
        
        for pair_name, stats in pair_stats.items():
            print(f"\n{pair_name} ({stats['service1_name']} vs {stats['service2_name']}):")
            print(f"  Blocks processed: {stats['total_blocks']}")
            print(f"  Total matching tweaks: {stats['total_matching']}")
            print(f"  Total {stats['service1_name']} unique: {stats['total_service1_unique']}")
            print(f"  Total {stats['service2_name']} unique: {stats['total_service2_unique']}")
            
            total_unique = stats['total_matching'] + stats['total_service1_unique'] + stats['total_service2_unique']
            if total_unique > 0:
                match_pct = (stats['total_matching'] / total_unique) * 100
                print(f"  Overall match percentage: {match_pct:.1f}%")
    
    if detailed:
        print("\nDetailed results by block:")
        for block_result in result.block_results:
            print(f"\n  Block {block_result.block_height}:")
            for service_name, count in block_result.tweak_counts.items():
                print(f"    {service_name}: {count} tweaks")
            
            # Print pairwise comparisons for this block if requested
            if service_pairs:
                pairwise_comparisons = block_result.pairwise_comparisons(service_pairs)
                for comparison in pairwise_comparisons:
                    print(f"    {comparison.pair_name}: {len(comparison.matching_tweaks)} matching, "
                          f"{len(comparison.service1_unique)} + {len(comparison.service2_unique)} unique")


async def _audit_common_config(args):
    """Shared config and validation logic for audit commands."""
    config_manager = ConfigManager(args.config)
    if not config_manager.services:
        print("Error: No services configured. Use -c or copy sample.config.json to config.json")
        return None, None, 1
    issues = config_manager.validate_config()
    if issues:
        print("Configuration validation failed:")
        for issue in issues:
            print(f"  - {issue}")
        return None, None, 1
    
    # Pass ignore-filter-mismatch flag to the auditor
    ignore_filter_mismatch = getattr(args, 'ignore_filter_mismatch', False)
    auditor = TweakServiceAuditor(config_manager.services, ignore_filter_mismatch=ignore_filter_mismatch)
    return auditor, config_manager.get_active_service_pairs(), 0


async def audit_single_block(args):
    """Audit a single block (uses shared config/validation logic)"""
    auditor, service_pairs, err = await _audit_common_config(args)
    if err:
        return err
    try:
        result = await auditor.audit_block(args.block)
        ignore_filter_mismatch = getattr(args, 'ignore_filter_mismatch', False)
        print_audit_result(result, args.detailed, service_pairs, auditor.services, ignore_filter_mismatch)
        
        # Store test data if requested
        store_test_flag = getattr(args, 'store_test', False)
        if store_test_flag:
            # Extract reference service name if specified (store_test can be True or a service name)
            reference_service = store_test_flag if isinstance(store_test_flag, str) else None
            store_test_data(result, auditor.services, reference_service)
        
        if args.output:
            output_data = {
                'block_height': result.block_height,
                'timestamp': result.service_results[0].request_time if result.service_results else 0,
                'services': result.total_services,
                'successful_services': result.successful_services,
                'tweak_counts': result.tweak_counts,
                'matching_tweaks': len(result.matching_tweaks),
                'non_matching_by_service': {k: len(v) for k, v in result.non_matching_by_service.items()}
            }
            
            # Add pairwise comparisons to output data
            if service_pairs:
                pairwise_comparisons = result.pairwise_comparisons(service_pairs)
                output_data['pairwise_comparisons'] = [
                    {
                        'pair_name': comp.pair_name,
                        'service1_name': comp.service1_name,
                        'service2_name': comp.service2_name,
                        'service1_tweaks': len(comp.service1_tweaks),
                        'service2_tweaks': len(comp.service2_tweaks),
                        'matching_tweaks': len(comp.matching_tweaks),
                        'service1_unique': list(comp.service1_unique) if args.detailed else len(comp.service1_unique),
                        'service2_unique': list(comp.service2_unique) if args.detailed else len(comp.service2_unique),
                        'match_percentage': comp.match_percentage
                    }
                    for comp in pairwise_comparisons
                ]
            
            with open(args.output, 'w') as f:
                json.dump(output_data, f, indent=2)
            print(f"\nResults saved to {args.output}")
        return 0
    except Exception as e:
        print(f"Error during audit: {e}")
        return 1


async def audit_block_range(args):
    """Audit a range of blocks (uses shared config/validation logic)"""
    auditor, service_pairs, err = await _audit_common_config(args)
    if err:
        return err
    try:
        # Determine output file for streaming detailed results
        detailed_output_file = None
        if args.output and args.detailed:
            # For detailed output, stream to a separate file and create summary in main output
            detailed_output_file = f"{args.output}.detailed.json"
            print(f"Detailed block results will be streamed to {detailed_output_file}")
        elif args.output:
            # For non-detailed output, stream directly to main output file
            detailed_output_file = args.output
        
        # Get batch size from args
        batch_size = getattr(args, 'batch_size', 200)
        
        result = await auditor.audit_range(
            args.start_block, 
            args.end_block, 
            batch_size=batch_size,
            output_file=detailed_output_file
        )
        print_range_result(result, args.detailed, service_pairs)
        
        # Create summary output if detailed streaming was used
        if args.output and args.detailed and detailed_output_file != args.output:
            summary_data = {
                'start_block': result.start_block,
                'end_block': result.end_block,
                'total_blocks_audited': result.total_blocks_audited,
                'summary_by_service': result.summary_by_service,
                'total_request_time_by_service': result.total_request_time_by_service,
                'detailed_results_file': detailed_output_file
            }
            with open(args.output, 'w') as f:
                json.dump(summary_data, f, indent=2)
            print(f"\nSummary saved to {args.output}")
            print(f"Detailed results saved to {detailed_output_file}")
        elif args.output and not args.detailed:
            print(f"\nResults saved to {args.output}")
        
        return 0
    except Exception as e:
        print(f"Error during range audit: {e}")
        return 1


def manage_config(args):
    """Manage configuration"""
    config_manager = ConfigManager(args.config)
    
    if args.list:
        config_manager.print_services()
        return 0
    
    elif args.validate:
        issues = config_manager.validate_config()
        if issues:
            print("Configuration validation failed:")
            for issue in issues:
                print(f"  - {issue}")
            return 1
        else:
            print("Configuration is valid.")
            return 0
    
    else:
        print("No configuration action specified. Use --help for options.")
        return 1


def main():
    """Main CLI entry point"""
    # Common/global options that should work before or after the command
    # Use two parent parsers to avoid defaults overriding values when options
    # are provided only before or only after the subcommand.
    common_main = argparse.ArgumentParser(add_help=False)
    common_main.add_argument('--config', '-c', default='config.json',
                             help='Configuration file path (default: config.json)')
    common_main.add_argument('--verbose', '-v', action='count', default=0,
                             help='Increase verbosity: -v for INFO, -vv for DEBUG (default: WARNING+ERROR only)')
    common_main.add_argument('--detailed', '-d', action='store_true', default=False,
                             help='Show detailed results')
    common_main.add_argument('--output', '-o', default=None,
                             help='Save results to JSON file')
    common_main.add_argument('--store_test', metavar='SERVICE', nargs='?', const=True, default=False,
                             help='Store full tweak output for the block to test_data/ directory. Optionally specify service name to use as reference (default: first successful service)')
    common_main.add_argument('--ignore-filter-mismatch', action='store_true', default=False,
                             help='Ignore filter config mismatches when using test_data services (default: show warnings)')

    # For subparsers, suppress defaults so main-level values (or absence) persist
    common_sub = argparse.ArgumentParser(add_help=False)
    common_sub.add_argument('--config', '-c', default=argparse.SUPPRESS,
                            help='Configuration file path (default: config.json)')
    common_sub.add_argument('--verbose', '-v', action='count', default=argparse.SUPPRESS,
                            help='Increase verbosity: -v for INFO, -vv for DEBUG (default: WARNING+ERROR only)')
    common_sub.add_argument('--detailed', '-d', action='store_true', default=argparse.SUPPRESS,
                            help='Show detailed results')
    common_sub.add_argument('--output', '-o', default=argparse.SUPPRESS,
                            help='Save results to JSON file')
    common_sub.add_argument('--store_test', metavar='SERVICE', nargs='?', const=True, default=argparse.SUPPRESS,
                            help='Store full tweak output for the block to test_data/ directory. Optionally specify service name to use as reference (default: first successful service)')
    common_sub.add_argument('--ignore-filter-mismatch', action='store_true', default=argparse.SUPPRESS,
                            help='Ignore filter config mismatches when using test_data services (default: show warnings)')

    parser = argparse.ArgumentParser(
        description="Silent Payments Tweak Service Auditor",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Audit a single block (WARNING+ERROR only)
  python main.py block 800000
  
  # Audit with INFO level logging
  python main.py -v block 800000
  python main.py block 800000 -v
  
  # Audit with DEBUG level logging  
  python main.py -vv block 800000
  
  # Audit a range of blocks
  python main.py range 800000 800010
  
  # Audit with detailed output and save results
  python main.py block 800000 --detailed --output results.json
  
  # Store test data from a specific service
  python main.py block 800000 --store_test=bitcoin
  
  # Store test data from first successful service
  python main.py block 800000 --store_test
  
  # Use test data service (ignoring filter mismatches)
  python main.py -c test_config.json block 800000 --ignore-filter-mismatch
  
  # Options can appear before or after the command
  python main.py -c config.json block 800000 -vv
        """,
        parents=[common_main],
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Configuration management
    config_parser = subparsers.add_parser('config', help='Manage configuration', parents=[common_sub])
    config_parser.add_argument('--list', action='store_true',
                              help='List configured services')
    config_parser.add_argument('--validate', action='store_true',
                              help='Validate configuration')
    
    # Single block audit (alias old name for backwards compatibility)
    block_parser = subparsers.add_parser('block', aliases=['audit-block'], help='Audit a single block', parents=[common_sub])
    block_parser.add_argument('block', type=int, help='Block height to audit')
    
    # Range audit (alias old name for backwards compatibility)
    range_parser = subparsers.add_parser('range', aliases=['audit-range'], help='Audit a range of blocks', parents=[common_sub])
    range_parser.add_argument('start_block', type=int, help='Starting block height')
    range_parser.add_argument('end_block', type=int, help='Ending block height')
    range_parser.add_argument('--batch-size', type=int, default=200, help='Number of blocks to process in each batch (default: 200)')

    args = parser.parse_args()
    
    # Setup logging
    setup_logging(getattr(args, 'verbose', 0))
    
    if not args.command:
        parser.print_help()
        return 1
    
    # Run appropriate command
    if args.command == 'config':
        return manage_config(args)
    elif args.command == 'block':
        return asyncio.run(audit_single_block(args))
    elif args.command == 'range':
        return asyncio.run(audit_block_range(args))
    else:
        print(f"Unknown command: {args.command}")
        return 1


if __name__ == '__main__':
    sys.exit(main())
