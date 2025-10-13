#!/usr/bin/env python3
"""
Report generator for gpuhunt-collected GPU prices.
Displays prices and availability grouped by GPU type.
"""

import sys
import argparse
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from collections import defaultdict
from tabulate import tabulate
from colorama import init, Fore, Style

from database import PriceDatabase
from models import GPUInstance

# Initialize colorama
init(autoreset=True)


class GPUHuntReporter:
    """Generate reports from gpuhunt-collected data."""
    
    def __init__(self):
        self.db = PriceDatabase()
    
    def get_latest_by_gpu(self) -> Dict[str, List[GPUInstance]]:
        """
        Get latest prices grouped by GPU type.
        
        Returns:
            Dictionary mapping GPU type to list of instances
        """
        instances = self.db.get_latest_prices()
        
        by_gpu = defaultdict(list)
        for inst in instances:
            by_gpu[inst.gpu_type].append(inst)
        
        # Sort instances within each GPU type by price
        for gpu_type in by_gpu:
            by_gpu[gpu_type].sort(key=lambda x: x.price_per_hour)
        
        return dict(by_gpu)
    
    def generate_summary_report(self, verbose: bool = False):
        """
        Generate summary report showing prices and availability by GPU.
        
        Args:
            verbose: Whether to show detailed information
        """
        print(f"\n{Fore.CYAN}{'='*80}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}GPU Price & Availability Report (GPUHunt Data){Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'='*80}{Style.RESET_ALL}\n")
        
        # Get stats
        stats = self.db.get_stats()
        
        if stats['total_records'] == 0:
            print(f"{Fore.YELLOW}No data available. Run collection first.{Style.RESET_ALL}")
            return
        
        print(f"Last Updated: {Fore.GREEN}{stats['last_snapshot']}{Style.RESET_ALL}")
        print(f"Total Instances: {stats['total_records']}")
        print(f"Providers: {stats['providers']}")
        print(f"GPU Types: {stats['gpu_types']}\n")
        
        # Group by GPU type
        by_gpu = self.get_latest_by_gpu()
        
        if not by_gpu:
            print(f"{Fore.YELLOW}No instances found in latest snapshot.{Style.RESET_ALL}")
            return
        
        # Display summary by GPU type
        print(f"{Fore.CYAN}{'='*80}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}Prices by GPU Type{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'='*80}{Style.RESET_ALL}\n")
        
        summary_rows = []
        for gpu_type in sorted(by_gpu.keys()):
            instances = by_gpu[gpu_type]
            prices = [i.price_per_hour for i in instances]
            providers = set(i.provider for i in instances)
            
            summary_rows.append([
                gpu_type,
                len(instances),
                ', '.join(sorted(providers)),
                f"${min(prices):.3f}",
                f"${max(prices):.3f}",
                f"${sum(prices)/len(prices):.3f}",
                f"${min(i.price_per_gpu_hour for i in instances):.3f}"
            ])
        
        headers = ['GPU Type', 'Instances', 'Providers', 'Min $/hr', 'Max $/hr', 'Avg $/hr', 'Best $/GPU/hr']
        print(tabulate(summary_rows, headers=headers, tablefmt='grid'))
        print()
        
        # Show detailed breakdown if verbose
        if verbose:
            print(f"\n{Fore.CYAN}{'='*80}{Style.RESET_ALL}")
            print(f"{Fore.CYAN}Detailed Pricing by GPU Type{Style.RESET_ALL}")
            print(f"{Fore.CYAN}{'='*80}{Style.RESET_ALL}\n")
            
            for gpu_type in sorted(by_gpu.keys()):
                instances = by_gpu[gpu_type]
                
                print(f"\n{Fore.YELLOW}=== {gpu_type} ({len(instances)} instances) ==={Style.RESET_ALL}\n")
                
                detail_rows = []
                for inst in instances[:10]:  # Show top 10 cheapest
                    detail_rows.append([
                        self._colorize_provider(inst.provider),
                        inst.instance_type,
                        inst.gpu_count,
                        inst.vcpus,
                        f"{inst.ram_gb:.0f}",
                        inst.region,
                        f"${inst.price_per_hour:.3f}",
                        f"${inst.price_per_gpu_hour:.3f}"
                    ])
                
                headers = ['Provider', 'Instance', 'GPUs', 'vCPUs', 'RAM (GB)', 'Region', '$/hr', '$/GPU/hr']
                print(tabulate(detail_rows, headers=headers, tablefmt='grid'))
                
                if len(instances) > 10:
                    print(f"\n  ... and {len(instances) - 10} more instances")
    
    def generate_provider_report(self):
        """Generate report grouped by provider."""
        print(f"\n{Fore.CYAN}{'='*80}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}Prices by Provider{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'='*80}{Style.RESET_ALL}\n")
        
        instances = self.db.get_latest_prices()
        
        by_provider = defaultdict(list)
        for inst in instances:
            by_provider[inst.provider].append(inst)
        
        provider_rows = []
        for provider in sorted(by_provider.keys()):
            insts = by_provider[provider]
            prices = [i.price_per_hour for i in insts]
            gpu_types = set(i.gpu_type for i in insts)
            
            provider_rows.append([
                self._colorize_provider(provider),
                len(insts),
                len(gpu_types),
                f"${min(prices):.3f}",
                f"${max(prices):.3f}",
                f"${sum(prices)/len(prices):.3f}"
            ])
        
        headers = ['Provider', 'Instances', 'GPU Types', 'Min $/hr', 'Max $/hr', 'Avg $/hr']
        print(tabulate(provider_rows, headers=headers, tablefmt='grid'))
        print()
    
    def generate_best_deals_report(self, gpu_type: Optional[str] = None, limit: int = 10):
        """
        Generate report of best deals.
        
        Args:
            gpu_type: Optional GPU type filter
            limit: Number of deals to show
        """
        print(f"\n{Fore.CYAN}{'='*80}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}Best Deals{Style.RESET_ALL}")
        if gpu_type:
            print(f"{Fore.CYAN}GPU Type: {gpu_type}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'='*80}{Style.RESET_ALL}\n")
        
        instances = self.db.get_latest_prices()
        
        if gpu_type:
            instances = [i for i in instances if gpu_type.upper() in i.gpu_type.upper()]
        
        if not instances:
            print(f"{Fore.YELLOW}No instances found.{Style.RESET_ALL}")
            return
        
        # Sort by price per GPU hour
        instances.sort(key=lambda x: x.price_per_gpu_hour)
        
        deal_rows = []
        for inst in instances[:limit]:
            deal_rows.append([
                self._colorize_provider(inst.provider),
                inst.instance_type,
                inst.gpu_type,
                inst.gpu_count,
                inst.vcpus,
                f"{inst.ram_gb:.0f}",
                inst.region,
                f"${inst.price_per_hour:.3f}",
                f"${inst.price_per_gpu_hour:.3f}"
            ])
        
        headers = ['Provider', 'Instance', 'GPU', 'GPUs', 'vCPUs', 'RAM (GB)', 'Region', '$/hr', '$/GPU/hr']
        print(tabulate(deal_rows, headers=headers, tablefmt='grid'))
        print()
    
    def generate_availability_report(self):
        """Generate availability report."""
        print(f"\n{Fore.CYAN}{'='*80}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}Availability by Region{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'='*80}{Style.RESET_ALL}\n")
        
        instances = self.db.get_latest_prices()
        
        by_region = defaultdict(lambda: defaultdict(int))
        for inst in instances:
            by_region[inst.region][inst.gpu_type] += inst.gpu_count
        
        region_rows = []
        for region in sorted(by_region.keys()):
            gpu_counts = by_region[region]
            total_gpus = sum(gpu_counts.values())
            gpu_types = len(gpu_counts)
            
            top_gpu = max(gpu_counts.items(), key=lambda x: x[1])
            
            region_rows.append([
                region,
                total_gpus,
                gpu_types,
                f"{top_gpu[0]} ({top_gpu[1]})"
            ])
        
        headers = ['Region', 'Total GPUs', 'GPU Types', 'Most Common']
        print(tabulate(region_rows, headers=headers, tablefmt='grid'))
        print()
    
    def _colorize_provider(self, provider: str) -> str:
        """Add color to provider names."""
        colors = {
            'aws': Fore.YELLOW,
            'gcp': Fore.BLUE,
            'azure': Fore.CYAN,
            'lambda': Fore.MAGENTA,
            'runpod': Fore.GREEN,
            'vastai': Fore.RED,
            'tensordock': Fore.LIGHTMAGENTA_EX,
            'datacrunch': Fore.LIGHTBLUE_EX,
            'cudo': Fore.LIGHTGREEN_EX,
            'nebius': Fore.LIGHTYELLOW_EX
        }
        color = colors.get(provider.lower(), Fore.WHITE)
        return f"{color}{provider.upper()}{Style.RESET_ALL}"


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Generate GPU price reports from gpuhunt data'
    )
    parser.add_argument(
        '--summary',
        action='store_true',
        help='Generate summary report (default)'
    )
    parser.add_argument(
        '--providers',
        action='store_true',
        help='Generate provider-based report'
    )
    parser.add_argument(
        '--best-deals',
        action='store_true',
        help='Show best deals'
    )
    parser.add_argument(
        '--availability',
        action='store_true',
        help='Show availability by region'
    )
    parser.add_argument(
        '--all',
        action='store_true',
        help='Generate all reports'
    )
    parser.add_argument(
        '--gpu-type',
        type=str,
        help='Filter by GPU type (for best deals)'
    )
    parser.add_argument(
        '--limit',
        type=int,
        default=10,
        help='Limit results (default: 10)'
    )
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Verbose output with detailed pricing'
    )
    
    args = parser.parse_args()
    
    reporter = GPUHuntReporter()
    
    # Default to summary if no specific report requested
    if not any([args.summary, args.providers, args.best_deals, args.availability, args.all]):
        args.summary = True
    
    try:
        if args.all or args.summary:
            reporter.generate_summary_report(verbose=args.verbose)
        
        if args.all or args.providers:
            reporter.generate_provider_report()
        
        if args.all or args.best_deals:
            reporter.generate_best_deals_report(
                gpu_type=args.gpu_type,
                limit=args.limit
            )
        
        if args.all or args.availability:
            reporter.generate_availability_report()
        
        sys.exit(0)
    
    except Exception as e:
        print(f"{Fore.RED}ERROR: {e}{Style.RESET_ALL}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()

