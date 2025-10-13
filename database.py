"""Database module for storing historical GPU pricing data."""

import sqlite3
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from pathlib import Path
import json

from models import GPUInstance


class PriceDatabase:
    """SQLite database for storing historical GPU pricing data."""
    
    def __init__(self, db_path: str = "data/gpu_prices.db"):
        """
        Initialize the database.
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
    
    def _init_db(self):
        """Initialize database schema."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Create prices table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS gpu_prices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TIMESTAMP NOT NULL,
                provider TEXT NOT NULL,
                instance_type TEXT NOT NULL,
                gpu_type TEXT NOT NULL,
                gpu_count INTEGER NOT NULL,
                gpu_memory_gb INTEGER,
                vcpus INTEGER NOT NULL,
                ram_gb REAL NOT NULL,
                region TEXT NOT NULL,
                price_per_hour REAL NOT NULL,
                available BOOLEAN,
                availability_zone TEXT,
                UNIQUE(timestamp, provider, instance_type, region)
            )
        """)
        
        # Create indexes for faster queries
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_timestamp 
            ON gpu_prices(timestamp)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_provider_instance 
            ON gpu_prices(provider, instance_type)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_gpu_type 
            ON gpu_prices(gpu_type)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_region 
            ON gpu_prices(region)
        """)
        
        # Create summary statistics table for quick aggregations
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS price_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TIMESTAMP NOT NULL UNIQUE,
                total_instances INTEGER NOT NULL,
                providers_count INTEGER NOT NULL,
                gpu_types_count INTEGER NOT NULL,
                min_price REAL NOT NULL,
                max_price REAL NOT NULL,
                avg_price REAL NOT NULL,
                metadata TEXT
            )
        """)
        
        conn.commit()
        conn.close()
    
    def store_prices(self, instances: List[GPUInstance], timestamp: Optional[datetime] = None) -> int:
        """
        Store GPU pricing data in the database.
        
        Args:
            instances: List of GPUInstance objects
            timestamp: Optional timestamp (defaults to now)
            
        Returns:
            Number of records inserted
        """
        if timestamp is None:
            timestamp = datetime.now()
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        inserted = 0
        for inst in instances:
            try:
                cursor.execute("""
                    INSERT OR REPLACE INTO gpu_prices (
                        timestamp, provider, instance_type, gpu_type, gpu_count,
                        gpu_memory_gb, vcpus, ram_gb, region, price_per_hour,
                        available, availability_zone
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    timestamp,
                    inst.provider,
                    inst.instance_type,
                    inst.gpu_type,
                    inst.gpu_count,
                    inst.gpu_memory_gb,
                    inst.vcpus,
                    inst.ram_gb,
                    inst.region,
                    inst.price_per_hour,
                    inst.available,
                    inst.availability_zone
                ))
                inserted += 1
            except sqlite3.IntegrityError:
                # Record already exists for this timestamp
                pass
        
        # Store snapshot metadata
        self._store_snapshot(cursor, timestamp, instances)
        
        conn.commit()
        conn.close()
        
        return inserted
    
    def _store_snapshot(self, cursor, timestamp: datetime, instances: List[GPUInstance]):
        """Store summary snapshot."""
        providers = set(i.provider for i in instances)
        gpu_types = set(i.gpu_type for i in instances)
        prices = [i.price_per_hour for i in instances]
        
        metadata = {
            'providers': list(providers),
            'gpu_types': list(gpu_types)
        }
        
        cursor.execute("""
            INSERT OR REPLACE INTO price_snapshots (
                timestamp, total_instances, providers_count, gpu_types_count,
                min_price, max_price, avg_price, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            timestamp,
            len(instances),
            len(providers),
            len(gpu_types),
            min(prices) if prices else 0,
            max(prices) if prices else 0,
            sum(prices) / len(prices) if prices else 0,
            json.dumps(metadata)
        ))
    
    def get_latest_prices(self, provider: Optional[str] = None) -> List[GPUInstance]:
        """
        Get the most recent prices.
        
        Args:
            provider: Optional provider filter
            
        Returns:
            List of GPUInstance objects
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get latest timestamp
        cursor.execute("SELECT MAX(timestamp) FROM gpu_prices")
        latest_timestamp = cursor.fetchone()[0]
        
        if not latest_timestamp:
            conn.close()
            return []
        
        # Get prices for latest timestamp
        query = "SELECT * FROM gpu_prices WHERE timestamp = ?"
        params = [latest_timestamp]
        
        if provider:
            query += " AND provider = ?"
            params.append(provider)
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()
        
        return [self._row_to_instance(row) for row in rows]
    
    def get_price_history(
        self,
        instance_type: str,
        provider: str,
        region: str,
        days: int = 7
    ) -> List[Dict[str, Any]]:
        """
        Get price history for a specific instance.
        
        Args:
            instance_type: Instance type
            provider: Cloud provider
            region: Region
            days: Number of days to look back
            
        Returns:
            List of price records with timestamps
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cutoff = datetime.now() - timedelta(days=days)
        
        cursor.execute("""
            SELECT timestamp, price_per_hour, available
            FROM gpu_prices
            WHERE provider = ? AND instance_type = ? AND region = ?
                AND timestamp >= ?
            ORDER BY timestamp ASC
        """, (provider, instance_type, region, cutoff))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [
            {
                'timestamp': row[0],
                'price_per_hour': row[1],
                'available': row[2]
            }
            for row in rows
        ]
    
    def get_price_trends(
        self,
        gpu_type: Optional[str] = None,
        provider: Optional[str] = None,
        days: int = 30
    ) -> List[Dict[str, Any]]:
        """
        Get average price trends over time.
        
        Args:
            gpu_type: Optional GPU type filter
            provider: Optional provider filter
            days: Number of days to analyze
            
        Returns:
            List of average prices by timestamp
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cutoff = datetime.now() - timedelta(days=days)
        
        query = """
            SELECT timestamp, AVG(price_per_hour) as avg_price, 
                   MIN(price_per_hour) as min_price,
                   MAX(price_per_hour) as max_price,
                   COUNT(*) as instance_count
            FROM gpu_prices
            WHERE timestamp >= ?
        """
        params = [cutoff]
        
        if gpu_type:
            query += " AND gpu_type = ?"
            params.append(gpu_type)
        
        if provider:
            query += " AND provider = ?"
            params.append(provider)
        
        query += " GROUP BY timestamp ORDER BY timestamp ASC"
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()
        
        return [
            {
                'timestamp': row[0],
                'avg_price': row[1],
                'min_price': row[2],
                'max_price': row[3],
                'instance_count': row[4]
            }
            for row in rows
        ]
    
    def get_snapshots(self, days: int = 30) -> List[Dict[str, Any]]:
        """
        Get snapshot summaries.
        
        Args:
            days: Number of days to look back
            
        Returns:
            List of snapshot summaries
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cutoff = datetime.now() - timedelta(days=days)
        
        cursor.execute("""
            SELECT timestamp, total_instances, providers_count, gpu_types_count,
                   min_price, max_price, avg_price, metadata
            FROM price_snapshots
            WHERE timestamp >= ?
            ORDER BY timestamp ASC
        """, (cutoff,))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [
            {
                'timestamp': row[0],
                'total_instances': row[1],
                'providers_count': row[2],
                'gpu_types_count': row[3],
                'min_price': row[4],
                'max_price': row[5],
                'avg_price': row[6],
                'metadata': json.loads(row[7]) if row[7] else {}
            }
            for row in rows
        ]
    
    def _row_to_instance(self, row: tuple) -> GPUInstance:
        """Convert database row to GPUInstance."""
        return GPUInstance(
            provider=row[2],
            instance_type=row[3],
            gpu_type=row[4],
            gpu_count=row[5],
            gpu_memory_gb=row[6],
            vcpus=row[7],
            ram_gb=row[8],
            region=row[9],
            price_per_hour=row[10],
            available=row[11],
            availability_zone=row[12],
            last_updated=datetime.fromisoformat(row[1])
        )
    
    def get_stats(self) -> Dict[str, Any]:
        """Get database statistics."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT MIN(timestamp), MAX(timestamp), COUNT(DISTINCT timestamp) FROM gpu_prices")
        first, last, snapshot_count = cursor.fetchone()
        
        cursor.execute("SELECT COUNT(*) FROM gpu_prices")
        total_records = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(DISTINCT provider) FROM gpu_prices")
        provider_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(DISTINCT gpu_type) FROM gpu_prices")
        gpu_type_count = cursor.fetchone()[0]
        
        conn.close()
        
        return {
            'total_records': total_records,
            'snapshots': snapshot_count,
            'first_snapshot': first,
            'last_snapshot': last,
            'providers': provider_count,
            'gpu_types': gpu_type_count
        }

