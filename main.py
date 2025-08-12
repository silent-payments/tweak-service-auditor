"""
Command Line Interface for Silent Payments Tweak Service Auditor
"""
import argparse
import asyncio
import logging
import json
import sys
from typing import List

from auditor import TweakServiceAuditor
from config import ConfigManager
from models import AuditResult, RangeAuditResult, PairwiseComparison


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


def print_pairwise_comparisons(comparisons: List[PairwiseComparison], detailed: bool = False):
    """Print pairwise comparison results in a readable format"""
    if not comparisons:
        return
    
    print(f"\n=== Pairwise Service Comparisons ===")
    
    for comparison in comparisons:
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


def print_audit_result(result: AuditResult, detailed: bool = False, service_pairs: List = None):
    """Print audit result in a readable format"""
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
        print_pairwise_comparisons(pairwise_comparisons, detailed)


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
    auditor = TweakServiceAuditor(config_manager.services)
    return auditor, config_manager.get_active_service_pairs(), 0


async def audit_single_block(args):
    """Audit a single block (uses shared config/validation logic)"""
    auditor, service_pairs, err = await _audit_common_config(args)
    if err:
        return err
    try:
        result = await auditor.audit_block(args.block)
        print_audit_result(result, args.detailed, service_pairs)
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
        result = await auditor.audit_range(args.start_block, args.end_block)
        print_range_result(result, args.detailed, service_pairs)
        if args.output:
            output_data = {
                'start_block': result.start_block,
                'end_block': result.end_block,
                'total_blocks_audited': result.total_blocks_audited,
                'summary_by_service': result.summary_by_service,
                'block_results': []
            }
            for block_result in result.block_results:
                block_data = {
                    'block_height': block_result.block_height,
                    'tweak_counts': block_result.tweak_counts,
                    'matching_tweaks': len(block_result.matching_tweaks),
                    'non_matching_by_service': {k: len(v) for k, v in block_result.non_matching_by_service.items()}
                }
                # Add pairwise comparisons for this block
                if service_pairs:
                    pairwise_comparisons = block_result.pairwise_comparisons(service_pairs)
                    block_data['pairwise_comparisons'] = [
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
                output_data['block_results'].append(block_data)
            with open(args.output, 'w') as f:
                json.dump(output_data, f, indent=2)
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
