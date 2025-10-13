#!/usr/bin/env python3
"""
Generate daily summary plots for GPU prices and availability.
Creates two plots:
1. Average price per GPU for each GPU type
2. Number of instances available for each GPU type
"""

import sys
import argparse
from datetime import datetime
from pathlib import Path
from collections import defaultdict

try:
    import matplotlib
    matplotlib.use('Agg')  # Non-interactive backend
    import matplotlib.pyplot as plt
    import matplotlib.ticker as ticker
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False

from database import PriceDatabase


def get_gpu_summary(exclude_unknown=True):
    """
    Get summary statistics for all GPU types from latest snapshot.
    
    Args:
        exclude_unknown: Whether to exclude 'Unknown' GPU types
        
    Returns:
        Dictionary with GPU type statistics
    """
    db = PriceDatabase()
    instances = db.get_latest_prices()
    
    if not instances:
        return {}
    
    summary = defaultdict(lambda: {
        'count': 0,
        'total_price': 0,
        'prices_per_gpu': [],
        'providers': set()
    })
    
    for inst in instances:
        gpu_type = inst.gpu_type
        
        # Skip unknown GPUs if requested
        if exclude_unknown and gpu_type.upper() == 'UNKNOWN':
            continue
            
        summary[gpu_type]['count'] += 1
        summary[gpu_type]['total_price'] += inst.price_per_hour
        summary[gpu_type]['prices_per_gpu'].append(inst.price_per_gpu_hour)
        summary[gpu_type]['providers'].add(inst.provider)
    
    # Calculate averages
    result = {}
    for gpu_type, data in summary.items():
        result[gpu_type] = {
            'count': data['count'],
            'avg_price_per_gpu': sum(data['prices_per_gpu']) / len(data['prices_per_gpu']),
            'min_price_per_gpu': min(data['prices_per_gpu']),
            'max_price_per_gpu': max(data['prices_per_gpu']),
            'providers': len(data['providers'])
        }
    
    return result


def plot_average_prices(summary, output_file='reports/figures/gpu_avg_prices.png', top_n=25):
    """
    Create bar chart of average price per GPU for each GPU type.
    
    Args:
        summary: Dictionary of GPU statistics
        output_file: Path to save the plot
        top_n: Number of top GPU types to show (by instance count)
    """
    if not HAS_MATPLOTLIB:
        print("Error: matplotlib not installed. Install with: pip install matplotlib")
        return
    
    if not summary:
        print("No data available to plot")
        return
    
    # Sort by instance count and take top N
    sorted_gpus = sorted(summary.items(), key=lambda x: x[1]['count'], reverse=True)[:top_n]
    
    # Sort selected GPUs by average price
    sorted_gpus = sorted(sorted_gpus, key=lambda x: x[1]['avg_price_per_gpu'])
    
    gpu_types = [item[0] for item in sorted_gpus]
    avg_prices = [item[1]['avg_price_per_gpu'] for item in sorted_gpus]
    instance_counts = [item[1]['count'] for item in sorted_gpus]
    
    # Create figure
    fig, ax = plt.subplots(figsize=(14, 10))
    
    # Create bars with color gradient based on price
    colors = plt.cm.RdYlGn_r([p/max(avg_prices) for p in avg_prices])
    bars = ax.barh(gpu_types, avg_prices, color=colors, edgecolor='black', linewidth=0.5)
    
    # Add instance count labels
    for i, (bar, count) in enumerate(zip(bars, instance_counts)):
        width = bar.get_width()
        ax.text(width + max(avg_prices)*0.02, bar.get_y() + bar.get_height()/2,
                f'{count} instances',
                ha='left', va='center', fontsize=8, color='gray')
    
    # Formatting
    ax.set_xlabel('Average Price per GPU ($/hour)', fontsize=12, fontweight='bold')
    ax.set_ylabel('GPU Type', fontsize=12, fontweight='bold')
    ax.set_title(f'Average GPU Pricing - Top {len(gpu_types)} GPU Types by Instance Count\n'
                 f'Updated: {datetime.now().strftime("%Y-%m-%d %H:%M")}',
                 fontsize=14, fontweight='bold', pad=20)
    
    # Add price labels on bars
    for i, (bar, price) in enumerate(zip(bars, avg_prices)):
        ax.text(bar.get_width()/2, bar.get_y() + bar.get_height()/2,
                f'${price:.2f}',
                ha='center', va='center', fontsize=9, fontweight='bold', color='white')
    
    # Grid
    ax.grid(axis='x', alpha=0.3, linestyle='--')
    ax.set_axisbelow(True)
    
    # Format x-axis
    ax.xaxis.set_major_formatter(ticker.FormatStrFormatter('$%.2f'))
    
    plt.tight_layout()
    
    # Save plot
    Path(output_file).parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    print(f"✓ Saved price plot to: {output_file}")
    plt.close()


def plot_instance_counts(summary, output_file='reports/figures/gpu_instance_counts.png', top_n=25):
    """
    Create bar chart of instance count for each GPU type.
    
    Args:
        summary: Dictionary of GPU statistics
        output_file: Path to save the plot
        top_n: Number of top GPU types to show
    """
    if not HAS_MATPLOTLIB:
        print("Error: matplotlib not installed. Install with: pip install matplotlib")
        return
    
    if not summary:
        print("No data available to plot")
        return
    
    # Sort by instance count and take top N
    sorted_gpus = sorted(summary.items(), key=lambda x: x[1]['count'], reverse=True)[:top_n]
    
    gpu_types = [item[0] for item in sorted_gpus]
    counts = [item[1]['count'] for item in sorted_gpus]
    providers = [item[1]['providers'] for item in sorted_gpus]
    
    # Create figure
    fig, ax = plt.subplots(figsize=(14, 10))
    
    # Create bars with color gradient
    colors = plt.cm.viridis([c/max(counts) for c in counts])
    bars = ax.barh(gpu_types, counts, color=colors, edgecolor='black', linewidth=0.5)
    
    # Add provider count labels
    for i, (bar, prov_count) in enumerate(zip(bars, providers)):
        width = bar.get_width()
        ax.text(width + max(counts)*0.02, bar.get_y() + bar.get_height()/2,
                f'{prov_count} provider{"s" if prov_count > 1 else ""}',
                ha='left', va='center', fontsize=8, color='gray')
    
    # Formatting
    ax.set_xlabel('Number of Instances', fontsize=12, fontweight='bold')
    ax.set_ylabel('GPU Type', fontsize=12, fontweight='bold')
    ax.set_title(f'GPU Instance Availability - Top {len(gpu_types)} GPU Types\n'
                 f'Updated: {datetime.now().strftime("%Y-%m-%d %H:%M")}',
                 fontsize=14, fontweight='bold', pad=20)
    
    # Add count labels on bars
    for bar, count in zip(bars, counts):
        ax.text(bar.get_width()/2, bar.get_y() + bar.get_height()/2,
                f'{count}',
                ha='center', va='center', fontsize=10, fontweight='bold', color='white')
    
    # Grid
    ax.grid(axis='x', alpha=0.3, linestyle='--')
    ax.set_axisbelow(True)
    
    plt.tight_layout()
    
    # Save plot
    Path(output_file).parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    print(f"✓ Saved instance count plot to: {output_file}")
    plt.close()


def plot_price_vs_availability(summary, output_file='reports/figures/gpu_price_vs_availability.png', top_n=25):
    """
    Create scatter plot showing relationship between price and availability.
    
    Args:
        summary: Dictionary of GPU statistics
        output_file: Path to save the plot
        top_n: Number of GPU types to show
    """
    if not HAS_MATPLOTLIB:
        print("Error: matplotlib not installed. Install with: pip install matplotlib")
        return
    
    if not summary:
        print("No data available to plot")
        return
    
    # Sort by instance count and take top N
    sorted_gpus = sorted(summary.items(), key=lambda x: x[1]['count'], reverse=True)[:top_n]
    
    gpu_types = [item[0] for item in sorted_gpus]
    avg_prices = [item[1]['avg_price_per_gpu'] for item in sorted_gpus]
    counts = [item[1]['count'] for item in sorted_gpus]
    
    # Create figure
    fig, ax = plt.subplots(figsize=(14, 10))
    
    # Create scatter plot with size based on count
    scatter = ax.scatter(avg_prices, range(len(gpu_types)), 
                        s=[c*2 for c in counts], 
                        alpha=0.6, 
                        c=avg_prices,
                        cmap='RdYlGn_r',
                        edgecolors='black',
                        linewidth=1)
    
    # Add GPU labels
    for i, (gpu, price, count) in enumerate(zip(gpu_types, avg_prices, counts)):
        ax.text(price, i, f' {gpu} ({count})', 
               va='center', ha='left', fontsize=9)
    
    # Formatting
    ax.set_xlabel('Average Price per GPU ($/hour)', fontsize=12, fontweight='bold')
    ax.set_yticks([])
    ax.set_title(f'GPU Price vs Availability (bubble size = instance count)\n'
                 f'Updated: {datetime.now().strftime("%Y-%m-%d %H:%M")}',
                 fontsize=14, fontweight='bold', pad=20)
    
    # Add colorbar
    cbar = plt.colorbar(scatter, ax=ax)
    cbar.set_label('Price ($/GPU/hour)', fontsize=10, fontweight='bold')
    
    # Grid
    ax.grid(axis='x', alpha=0.3, linestyle='--')
    ax.set_axisbelow(True)
    
    # Format x-axis
    ax.xaxis.set_major_formatter(ticker.FormatStrFormatter('$%.2f'))
    
    plt.tight_layout()
    
    # Save plot
    Path(output_file).parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    print(f"✓ Saved price vs availability plot to: {output_file}")
    plt.close()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Generate daily GPU summary plots'
    )
    parser.add_argument(
        '--top-n',
        type=int,
        default=25,
        help='Number of top GPU types to show (default: 25)'
    )
    parser.add_argument(
        '--include-unknown',
        action='store_true',
        help='Include "Unknown" GPU types in plots'
    )
    parser.add_argument(
        '--prices-only',
        action='store_true',
        help='Generate only the price plot'
    )
    parser.add_argument(
        '--counts-only',
        action='store_true',
        help='Generate only the instance count plot'
    )
    parser.add_argument(
        '--output-dir',
        type=str,
        default='reports/figures',
        help='Output directory for plots (default: reports/figures)'
    )
    
    args = parser.parse_args()
    
    if not HAS_MATPLOTLIB:
        print("Error: matplotlib not installed. Install with: pip install matplotlib")
        sys.exit(1)
    
    print(f"\nGenerating GPU summary plots...")
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    # Get summary data
    summary = get_gpu_summary(exclude_unknown=not args.include_unknown)
    
    if not summary:
        print("No data available in database. Run collection first:")
        print("  python3 collect_prices_gpuhunt.py -v")
        sys.exit(1)
    
    print(f"Found {len(summary)} GPU types in database")
    print(f"Generating plots for top {args.top_n} GPU types...\n")
    
    # Create output directory
    Path(args.output_dir).mkdir(parents=True, exist_ok=True)
    
    # Generate plots
    if not args.counts_only:
        plot_average_prices(
            summary, 
            output_file=f'{args.output_dir}/gpu_avg_prices.png',
            top_n=args.top_n
        )
    
    if not args.prices_only:
        plot_instance_counts(
            summary,
            output_file=f'{args.output_dir}/gpu_instance_counts.png',
            top_n=args.top_n
        )
    
    # Always generate the combined plot
    if not args.prices_only and not args.counts_only:
        plot_price_vs_availability(
            summary,
            output_file=f'{args.output_dir}/gpu_price_vs_availability.png',
            top_n=args.top_n
        )
    
    print(f"\n✓ All plots saved to: {args.output_dir}/")
    print(f"\nView plots:")
    print(f"  ls -lh {args.output_dir}/*.png")


if __name__ == '__main__':
    main()

