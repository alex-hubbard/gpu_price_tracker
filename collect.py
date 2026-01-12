#!/usr/bin/env python3
"""
GPUHunt-based price collection script.
Fetches and stores GPU prices using the gpuhunt module.
"""

import sys
import argparse
from datetime import datetime
from typing import List, Optional
from pathlib import Path
import warnings

try:
    import gpuhunt
    # Monkey-patch TensorDock provider to handle API response format changes
    try:
        from gpuhunt.providers.tensordock import TensorDockProvider
        import requests
        import functools
        
        # Store original get method
        _original_tensordock_get = TensorDockProvider.get
        
        @functools.wraps(_original_tensordock_get)
        def _patched_tensordock_get(self, query_filter=None, balance_resources=True):
            """Patched version that handles missing 'hostnodes' key in API response."""
            import logging
            logger = logging.getLogger(__name__)
            logger.info("Fetching TensorDock offers")
            
            try:
                # Get the marketplace URL (from the original implementation)
                marketplace_hostnodes_url = "https://marketplace.tensordock.com/api/v0/client/hostnodes"
                response = requests.get(marketplace_hostnodes_url, timeout=10)
                response.raise_for_status()
                data = response.json()
                
                # Handle case where 'hostnodes' key is missing or API format changed
                if "hostnodes" not in data:
                    # API format may have changed - log and return empty list
                    logger.warning(
                        "TensorDock API response missing 'hostnodes' key. "
                        "Response keys: %s. API may have changed format.",
                        list(data.keys())
                    )
                    # Return empty list - provider is unavailable but won't crash
                    return []
                
                # If hostnodes exists, proceed with original logic
                # We need to temporarily patch the requests.get call within the original method
                # Since we can't easily do that, we'll manually construct the call
                # But actually, the simplest is to just catch the KeyError and handle it
                hostnodes = data["hostnodes"]
                
                # Now we need to execute the original logic with the safe hostnodes
                # Since we have the data, let's manually execute the logic from the original method
                from gpuhunt._internal.models import RawCatalogItem
                from gpuhunt.providers.tensordock import convert_gpu_name, round_down
                
                offers = []
                for hostnode, details in hostnodes.items():
                    location = details["location"]["country"].lower().replace(" ", "")
                    if query_filter is not None:
                        offers += self.optimize_offers(
                            query_filter,
                            details["specs"],
                            hostnode,
                            location,
                            balance_resources=balance_resources,
                        )
                    else:  # pick maximum possible configuration
                        for gpu_name, gpu in details["specs"]["gpu"].items():
                            if gpu["amount"] == 0:
                                continue
                            offers.append(
                                RawCatalogItem(
                                    instance_name=hostnode,
                                    location=location,
                                    price=round(
                                        sum(
                                            details["specs"][key]["price"]
                                            * details["specs"][key]["amount"]
                                            for key in ("cpu", "ram", "storage")
                                        )
                                        + gpu["amount"] * gpu["price"],
                                        5,
                                    ),
                                    cpu=round_down(details["specs"]["cpu"]["amount"], 2),
                                    memory=float(round_down(details["specs"]["ram"]["amount"], 2)),
                                    gpu_vendor=None,
                                    gpu_count=gpu["amount"],
                                    gpu_name=convert_gpu_name(gpu_name),
                                    gpu_memory=float(gpu["vram"]),
                                    spot=False,
                                    disk_size=float(details["specs"]["storage"]["amount"]),
                                )
                            )
                return sorted(offers, key=lambda i: i.price)
                
            except KeyError as e:
                if "hostnodes" in str(e) or "'hostnodes'" in str(e):
                    logger.warning("TensorDock API response format changed - 'hostnodes' key missing. Skipping provider.")
                    return []
                # Re-raise other KeyErrors
                raise
            except Exception as e:
                logger.warning("Error fetching TensorDock offers: %s", e)
                # Return empty list instead of crashing
                return []
        
        # Apply the patch
        TensorDockProvider.get = _patched_tensordock_get
        
    except (ImportError, AttributeError):
        # If TensorDock provider is not available or structure changed, continue without patch
        pass
        
except ImportError:
    print("ERROR: gpuhunt module not installed. Run: pip install gpuhunt", file=sys.stderr)
    sys.exit(1)


from models import GPUInstance
from database import PriceDatabase


def convert_gpuhunt_to_instance(item) -> Optional[GPUInstance]:
    """
    Convert gpuhunt catalog item to GPUInstance.
    
    Args:
        item: gpuhunt catalog item
        
    Returns:
        GPUInstance object or None if conversion fails
    """
    try:
        # Extract GPU information
        gpu_name = getattr(item, 'gpu_name', None) or getattr(item, 'name', 'Unknown')
        gpu_count = getattr(item, 'gpu_count', 1)
        gpu_memory = getattr(item, 'gpu_memory', None)
        
        # Extract instance information
        instance_name = getattr(item, 'instance_name', None) or getattr(item, 'name', 'unknown')
        cpu = getattr(item, 'cpu', 0)
        memory = getattr(item, 'memory', 0)
        
        # Extract location information
        location = getattr(item, 'location', 'unknown')
        provider = getattr(item, 'provider', 'unknown')
        
        # Extract pricing
        price = getattr(item, 'price', 0.0)
        
        # Extract spot pricing information
        is_spot = getattr(item, 'spot', False)
        
        # Map provider names to standard format
        provider_map = {
            'aws': 'aws',
            'gcp': 'gcp',
            'azure': 'azure',
            'lambda': 'lambda',
            'runpod': 'runpod',
            'tensordock': 'tensordock',
            'vastai': 'vastai',
            'datacrunch': 'datacrunch',
            'cudo': 'cudo',
            'nebius': 'nebius'
        }
        
        provider_lower = provider.lower()
        normalized_provider = provider_map.get(provider_lower, provider_lower)
        
        return GPUInstance(
            provider=normalized_provider,
            instance_type=instance_name,
            gpu_type=gpu_name,
            gpu_count=gpu_count,
            gpu_memory_gb=int(gpu_memory) if gpu_memory else None,
            vcpus=int(cpu) if cpu else 0,
            ram_gb=float(memory) if memory else 0.0,
            region=location,
            price_per_hour=float(price),
            is_spot=bool(is_spot),
            available=True,  # gpuhunt typically returns available instances
            availability_zone=None
        )
    except Exception as e:
        print(f"WARNING: Failed to convert gpuhunt item: {e}", file=sys.stderr)
        return None


def collect_gpuhunt_prices(
    min_gpu_memory: Optional[int] = None,
    min_cpu: Optional[int] = None,
    max_price: Optional[float] = None,
    gpu_name: Optional[str] = None,
    provider: Optional[str] = None,
    verbose: bool = False
) -> List[GPUInstance]:
    """
    Collect prices from gpuhunt.
    
    Args:
        min_gpu_memory: Minimum GPU memory in GB
        min_cpu: Minimum number of CPUs
        max_price: Maximum price per hour
        gpu_name: Filter by GPU name (e.g., 'A100', 'H100')
        provider: Filter by provider
        verbose: Whether to print detailed output
        
    Returns:
        List of GPUInstance objects
    """
    if verbose:
        print("Fetching GPU prices from gpuhunt...")
    
    try:
        # Query gpuhunt catalog
        # Build query parameters
        query_params = {}
        if min_gpu_memory:
            query_params['min_gpu_memory'] = min_gpu_memory
        if min_cpu:
            query_params['min_cpu'] = min_cpu
        if max_price:
            query_params['max_price'] = max_price
        if gpu_name:
            query_params['gpu_name'] = gpu_name
        if provider:
            query_params['provider'] = provider
        
        # Suppress warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            # Get catalog items
            if query_params:
                items = gpuhunt.query(**query_params)
            else:
                # Get all available instances
                items = gpuhunt.query()
        
        if verbose:
            print(f"  Retrieved {len(items) if hasattr(items, '__len__') else 'unknown'} items from gpuhunt")
        
        # Convert to GPUInstance objects
        instances = []
        for item in items:
            gpu_instance = convert_gpuhunt_to_instance(item)
            if gpu_instance:
                instances.append(gpu_instance)
        
        if verbose:
            print(f"  Converted {len(instances)} valid instances")
        
        return instances
    
    except Exception as e:
        # Handle errors gracefully
        if verbose:
            print(f"ERROR querying gpuhunt: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc()
        else:
            print(f"WARNING: Error querying gpuhunt (some providers may be unavailable): {type(e).__name__}", file=sys.stderr)
        return []


def collect_all_prices(verbose: bool = False) -> tuple[int, int]:
    """
    Collect prices from gpuhunt and store in database.
    
    Args:
        verbose: Whether to print detailed output
        
    Returns:
        Tuple of (total_instances, stored_count)
    """
    timestamp = datetime.now()
    
    if verbose:
        print(f"[{timestamp.strftime('%Y-%m-%d %H:%M:%S')}] Starting gpuhunt price collection...")
    
    # Collect all available GPU instances
    instances = collect_gpuhunt_prices(verbose=verbose)
    
    if not instances:
        print("WARNING: No instances collected from gpuhunt", file=sys.stderr)
        return 0, 0
    
    # Store in database
    if verbose:
        print(f"  Total instances collected: {len(instances)}")
        print("  Storing to database...")
    
    db = PriceDatabase()
    stored = db.store_prices(instances, timestamp=timestamp)
    
    if verbose:
        print(f"  Stored {stored} price records")
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Collection complete!")
    
    return len(instances), stored


def main():
    """Main entry point for gpuhunt-based collection."""
    parser = argparse.ArgumentParser(
        description='Collect GPU prices using gpuhunt module'
    )
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Verbose output'
    )
    parser.add_argument(
        '--stats',
        action='store_true',
        help='Show database statistics after collection'
    )
    parser.add_argument(
        '--min-gpu-memory',
        type=int,
        help='Minimum GPU memory in GB'
    )
    parser.add_argument(
        '--min-cpu',
        type=int,
        help='Minimum number of CPUs'
    )
    parser.add_argument(
        '--max-price',
        type=float,
        help='Maximum price per hour'
    )
    parser.add_argument(
        '--gpu-name',
        type=str,
        help='Filter by GPU name (e.g., A100, H100)'
    )
    parser.add_argument(
        '--provider',
        type=str,
        help='Filter by provider'
    )
    
    args = parser.parse_args()
    
    try:
        # If filters are specified, use custom query
        if any([args.min_gpu_memory, args.min_cpu, args.max_price, args.gpu_name, args.provider]):
            instances = collect_gpuhunt_prices(
                min_gpu_memory=args.min_gpu_memory,
                min_cpu=args.min_cpu,
                max_price=args.max_price,
                gpu_name=args.gpu_name,
                provider=args.provider,
                verbose=args.verbose
            )
            
            if instances:
                db = PriceDatabase()
                timestamp = datetime.now()
                stored = db.store_prices(instances, timestamp=timestamp)
                
                if args.verbose:
                    print(f"\nStored {stored} records to database")
                
                total, stored = len(instances), stored
            else:
                total, stored = 0, 0
        else:
            # Collect all prices
            total, stored = collect_all_prices(verbose=args.verbose)
        
        if args.stats:
            db = PriceDatabase()
            stats = db.get_stats()
            print("\nDatabase Statistics:")
            print(f"  Total records: {stats['total_records']}")
            print(f"  Snapshots: {stats['snapshots']}")
            print(f"  First snapshot: {stats['first_snapshot']}")
            print(f"  Last snapshot: {stats['last_snapshot']}")
            print(f"  Providers tracked: {stats['providers']}")
            print(f"  GPU types tracked: {stats['gpu_types']}")
        
        sys.exit(0)
    except Exception as e:
        print(f"FATAL ERROR: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()

