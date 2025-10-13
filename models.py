"""Data models for GPU instances and pricing information."""

from dataclasses import dataclass
from typing import Optional
from datetime import datetime


@dataclass
class GPUInstance:
    """Represents a GPU instance offering from a cloud provider."""
    
    provider: str  # 'aws', 'gcp', 'azure'
    instance_type: str  # e.g., 'p3.2xlarge', 'n1-standard-4-v100-1'
    gpu_type: str  # e.g., 'V100', 'A100', 'T4'
    gpu_count: int  # Number of GPUs
    gpu_memory_gb: Optional[int]  # GPU memory in GB
    vcpus: int  # Number of vCPUs
    ram_gb: float  # System RAM in GB
    region: str  # Cloud provider region
    price_per_hour: float  # On-demand price per hour in USD
    available: Optional[bool] = None  # Whether available in region
    availability_zone: Optional[str] = None  # Specific AZ if applicable
    last_updated: Optional[datetime] = None
    
    def __post_init__(self):
        if self.last_updated is None:
            self.last_updated = datetime.now()
    
    @property
    def price_per_gpu_hour(self) -> float:
        """Calculate price per GPU per hour."""
        if self.gpu_count > 0:
            return self.price_per_hour / self.gpu_count
        return 0.0
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            'provider': self.provider,
            'instance_type': self.instance_type,
            'gpu_type': self.gpu_type,
            'gpu_count': self.gpu_count,
            'gpu_memory_gb': self.gpu_memory_gb,
            'vcpus': self.vcpus,
            'ram_gb': self.ram_gb,
            'region': self.region,
            'price_per_hour': self.price_per_hour,
            'price_per_gpu_hour': self.price_per_gpu_hour,
            'available': self.available,
            'availability_zone': self.availability_zone,
            'last_updated': self.last_updated.isoformat() if self.last_updated else None
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'GPUInstance':
        """Create instance from dictionary."""
        # Remove computed property if present
        data = data.copy()
        data.pop('price_per_gpu_hour', None)
        
        if data.get('last_updated'):
            data['last_updated'] = datetime.fromisoformat(data['last_updated'])
        return cls(**data)

