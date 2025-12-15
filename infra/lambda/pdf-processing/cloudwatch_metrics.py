"""
CloudWatch Metrics Module for PDF Processing

This module provides utilities for sending custom metrics to CloudWatch
for monitoring PDF processing, API usage, and error rates.
"""

import boto3
import logging
import time
from datetime import datetime
from typing import Dict, Any, Optional, List
from enum import Enum
from contextlib import contextmanager

logger = logging.getLogger(__name__)

class MetricUnit(Enum):
    """CloudWatch metric units."""
    COUNT = "Count"
    SECONDS = "Seconds"
    MILLISECONDS = "Milliseconds"
    BYTES = "Bytes"
    PERCENT = "Percent"

class CloudWatchMetrics:
    """Utility class for sending custom metrics to CloudWatch."""
    
    def __init__(self, namespace: str = "GaTech/PDFProcessing"):
        """
        Initialize CloudWatch metrics client.
        
        Args:
            namespace: CloudWatch namespace for metrics
        """
        self.namespace = namespace
        try:
            self.cloudwatch = boto3.client('cloudwatch')
        except Exception as e:
            logger.warning(f"Failed to initialize CloudWatch client: {e}")
            self.cloudwatch = None
        self.metrics_buffer: List[Dict[str, Any]] = []
        self.max_buffer_size = 20  # CloudWatch limit
    
    def put_metric(
        self, 
        metric_name: str, 
        value: float, 
        unit: MetricUnit = MetricUnit.COUNT,
        dimensions: Optional[Dict[str, str]] = None,
        timestamp: Optional[datetime] = None
    ) -> None:
        """
        Add a metric to the buffer for batch sending.
        
        Args:
            metric_name: Name of the metric
            value: Metric value
            unit: Metric unit
            dimensions: Optional dimensions for the metric
            timestamp: Optional timestamp (defaults to now)
        """
        if not self.cloudwatch:
            return
            
        try:
            metric_data = {
                'MetricName': metric_name,
                'Value': value,
                'Unit': unit.value,
                'Timestamp': timestamp or datetime.utcnow()
            }
            
            if dimensions:
                metric_data['Dimensions'] = [
                    {'Name': k, 'Value': v} for k, v in dimensions.items()
                ]
            
            self.metrics_buffer.append(metric_data)
            
            # Send metrics if buffer is full
            if len(self.metrics_buffer) >= self.max_buffer_size:
                self.flush_metrics()
                
        except Exception as e:
            logger.warning(f"Failed to add metric {metric_name}: {e}")
    
    def flush_metrics(self) -> None:
        """Send all buffered metrics to CloudWatch."""
        if not self.metrics_buffer or not self.cloudwatch:
            return
        
        try:
            self.cloudwatch.put_metric_data(
                Namespace=self.namespace,
                MetricData=self.metrics_buffer
            )
            
            logger.debug(f"Sent {len(self.metrics_buffer)} metrics to CloudWatch")
            self.metrics_buffer.clear()
            
        except Exception as e:
            logger.error(f"Failed to send metrics to CloudWatch: {e}")
            # Clear buffer to prevent memory buildup
            self.metrics_buffer.clear()
    
    def increment_counter(
        self, 
        metric_name: str, 
        dimensions: Optional[Dict[str, str]] = None,
        value: float = 1.0
    ) -> None:
        """
        Increment a counter metric.
        
        Args:
            metric_name: Name of the counter metric
            dimensions: Optional dimensions for the metric
            value: Value to increment by (default 1.0)
        """
        self.put_metric(metric_name, value, MetricUnit.COUNT, dimensions)
    
    def record_api_call(
        self, 
        endpoint: str, 
        method: str, 
        status_code: int,
        duration_ms: float,
        error_category: Optional[str] = None
    ) -> None:
        """
        Record API call metrics.
        
        Args:
            endpoint: API endpoint path
            method: HTTP method
            status_code: HTTP status code
            duration_ms: Request duration in milliseconds
            error_category: Optional error category for failed requests
        """
        base_dimensions = {
            'Endpoint': endpoint,
            'Method': method,
            'StatusCode': str(status_code)
        }
        
        # Record API call count
        self.increment_counter('APIRequests', base_dimensions)
        
        # Record response time
        self.put_metric(
            'APIResponseTime', 
            duration_ms, 
            MetricUnit.MILLISECONDS,
            base_dimensions
        )
        
        # Record success/error metrics
        if 200 <= status_code < 300:
            self.increment_counter('APIRequestsSuccess', base_dimensions)
        else:
            error_dimensions = base_dimensions.copy()
            if error_category:
                error_dimensions['ErrorCategory'] = error_category
            
            self.increment_counter('APIRequestsError', error_dimensions)
    
    def __del__(self):
        """Ensure metrics are flushed when object is destroyed."""
        try:
            self.flush_metrics()
        except Exception:
            pass  # Ignore errors during cleanup

# Global metrics instance
_metrics_instance = None

def get_metrics() -> CloudWatchMetrics:
    """Get the global CloudWatch metrics instance."""
    global _metrics_instance
    if _metrics_instance is None:
        _metrics_instance = CloudWatchMetrics()
    return _metrics_instance