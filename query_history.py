#!/usr/bin/env python3
"""
Query historical pricing data and show trends.
"""

import sys
import argparse
from datetime import datetime, timedelta
from typing import Optional
from tabulate import tabulate
from colorama import init, Fore, Style

from database import PriceDatabase

init(autoreset=True)


def format_timestamp(ts_str: str) -> str:
    """Format timestamp for display."""
    dt = datetime.fromisoformat(ts_str)
    return dt.strftime('%Y-%m-%d %H:%M')


def show_instance_history(
    instance_type: str,
    provider: str,
    region: str,
    days: int = 7
):
    """Show price history for a specific instance."""
    db = PriceDatabase()
    history = db.get_price_history(instance_type, provider, region, days)
    
    if not history:
        print(f"{Fore.YELLOW}No historical data found for {provider} {instance_type} in {region}{Style.RESET_ALL}")
        return
    
    print(f"\n{Fore.CYAN}Price History: {provider.upper()} {instance_type} ({region}){Style.RESET_ALL}")
    print(f"Period: Last {days} days\n")
    
    headers = ['Timestamp', 'Price/hour', 'Available']
    rows = []
    
    for record in history:
        avail = '✓' if record['available'] else ('✗' if record['available'] is False else '?')
        rows.append([
            format_timestamp(record['timestamp']),
            f"${record['price_per_hour']:.3f}",
            avail
        ])
    
    print(tabulate(rows, headers=headers, tablefmt='grid'))
    
    # Calculate statistics
    prices = [r['price_per_hour'] for r in history]
    print(f"\n{Fore.GREEN}Statistics:{Style.RESET_ALL}")
    print(f"  Data points: {len(prices)}")
    print(f"  Current price: ${prices[-1]:.3f}/hour")
    print(f"  Min price: ${min(prices):.3f}/hour")
    print(f"  Max price: ${max(prices):.3f}/hour")
    print(f"  Avg price: ${sum(prices)/len(prices):.3f}/hour")
    
    # Show price change
    if len(prices) > 1:
        change = prices[-1] - prices[0]
        change_pct = (change / prices[0]) * 100
        color = Fore.GREEN if change <= 0 else Fore.RED
        print(f"  Change: {color}${change:+.3f} ({change_pct:+.1f}%){Style.RESET_ALL}")
    print()


def show_price_trends(
    gpu_type: Optional[str] = None,
    provider: Optional[str] = None,
    days: int = 30
):
    """Show price trends over time."""
    db = PriceDatabase()
    trends = db.get_price_trends(gpu_type, provider, days)
    
    if not trends:
        print(f"{Fore.YELLOW}No trend data found{Style.RESET_ALL}")
        return
    
    title = "Price Trends"
    if gpu_type:
        title += f" - {gpu_type}"
    if provider:
        title += f" ({provider.upper()})"
    
    print(f"\n{Fore.CYAN}{title}{Style.RESET_ALL}")
    print(f"Period: Last {days} days\n")
    
    headers = ['Timestamp', 'Avg Price', 'Min Price', 'Max Price', 'Instances']
    rows = []
    
    for record in trends:
        rows.append([
            format_timestamp(record['timestamp']),
            f"${record['avg_price']:.3f}",
            f"${record['min_price']:.3f}",
            f"${record['max_price']:.3f}",
            record['instance_count']
        ])
    
    print(tabulate(rows, headers=headers, tablefmt='grid'))
    
    # Show overall statistics
    avg_prices = [r['avg_price'] for r in trends]
    print(f"\n{Fore.GREEN}Overall Statistics:{Style.RESET_ALL}")
    print(f"  Snapshots: {len(avg_prices)}")
    print(f"  Current avg: ${avg_prices[-1]:.3f}/hour")
    print(f"  Lowest avg: ${min(avg_prices):.3f}/hour")
    print(f"  Highest avg: ${max(avg_prices):.3f}/hour")
    
    if len(avg_prices) > 1:
        change = avg_prices[-1] - avg_prices[0]
        change_pct = (change / avg_prices[0]) * 100
        color = Fore.GREEN if change <= 0 else Fore.RED
        print(f"  Trend: {color}${change:+.3f} ({change_pct:+.1f}%){Style.RESET_ALL}")
    print()


def show_snapshots(days: int = 30):
    """Show snapshot summaries."""
    db = PriceDatabase()
    snapshots = db.get_snapshots(days)
    
    if not snapshots:
        print(f"{Fore.YELLOW}No snapshots found{Style.RESET_ALL}")
        return
    
    print(f"\n{Fore.CYAN}Collection Snapshots{Style.RESET_ALL}")
    print(f"Period: Last {days} days\n")
    
    headers = ['Timestamp', 'Instances', 'Providers', 'GPU Types', 'Min $', 'Max $', 'Avg $']
    rows = []
    
    for snap in snapshots:
        rows.append([
            format_timestamp(snap['timestamp']),
            snap['total_instances'],
            snap['providers_count'],
            snap['gpu_types_count'],
            f"${snap['min_price']:.2f}",
            f"${snap['max_price']:.2f}",
            f"${snap['avg_price']:.2f}"
        ])
    
    print(tabulate(rows, headers=headers, tablefmt='grid'))
    print(f"\n{Fore.GREEN}Total snapshots: {len(snapshots)}{Style.RESET_ALL}\n")


def show_database_stats():
    """Show database statistics."""
    db = PriceDatabase()
    stats = db.get_stats()
    
    print(f"\n{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}Database Statistics{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}\n")
    
    print(f"Total price records: {stats['total_records']:,}")
    print(f"Number of snapshots: {stats['snapshots']}")
    print(f"Providers tracked: {stats['providers']}")
    print(f"GPU types tracked: {stats['gpu_types']}")
    
    if stats['first_snapshot']:
        first = datetime.fromisoformat(stats['first_snapshot'])
        last = datetime.fromisoformat(stats['last_snapshot'])
        duration = last - first
        
        print(f"\nTime Range:")
        print(f"  First snapshot: {first.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  Last snapshot:  {last.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  Duration: {duration.days} days, {duration.seconds // 3600} hours")
        
        if stats['snapshots'] > 1:
            avg_interval = duration.total_seconds() / (stats['snapshots'] - 1) / 3600
            print(f"  Avg collection interval: {avg_interval:.1f} hours")
    
    print()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Query historical GPU pricing data',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Show database statistics
  python query_history.py --stats
  
  # Show all snapshots from last 7 days
  python query_history.py --snapshots --days 7
  
  # Show price trends for A100 GPUs
  python query_history.py --trends --gpu-type A100 --days 30
  
  # Show price history for specific instance
  python query_history.py --instance p3.2xlarge --provider aws --region us-east-1
        """
    )
    
    parser.add_argument('--stats', action='store_true', help='Show database statistics')
    parser.add_argument('--snapshots', action='store_true', help='Show collection snapshots')
    parser.add_argument('--trends', action='store_true', help='Show price trends')
    parser.add_argument('--instance', type=str, help='Specific instance type to query')
    parser.add_argument('--provider', type=str, help='Provider (aws, gcp, azure)')
    parser.add_argument('--region', type=str, help='Region')
    parser.add_argument('--gpu-type', type=str, help='GPU type filter')
    parser.add_argument('--days', type=int, default=7, help='Number of days to look back (default: 7)')
    
    args = parser.parse_args()
    
    if args.stats:
        show_database_stats()
    
    if args.snapshots:
        show_snapshots(days=args.days)
    
    if args.trends:
        show_price_trends(gpu_type=args.gpu_type, provider=args.provider, days=args.days)
    
    if args.instance:
        if not args.provider or not args.region:
            print(f"{Fore.RED}Error: --instance requires --provider and --region{Style.RESET_ALL}")
            sys.exit(1)
        show_instance_history(args.instance, args.provider, args.region, days=args.days)
    
    if not any([args.stats, args.snapshots, args.trends, args.instance]):
        # Default: show stats
        show_database_stats()


if __name__ == '__main__':
    main()

