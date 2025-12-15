"""
Simplified Job Management Module for Georgia Tech Enrollment Data Processing

This module handles basic job status tracking with simplified S3 storage.
"""

import json
import logging
import uuid
import boto3
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from enum import Enum

logger = logging.getLogger(__name__)

class JobStatus(Enum):
    """Enumeration of possible job statuses."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

@dataclass
class JobParameters:
    """Parameters for enrollment data processing job."""
    nterms: int
    subjects: List[str]
    ranges: List[List[int]]
    include_summer: bool
    save_all: bool
    save_grouped: bool

@dataclass
class JobRecord:
    """Simplified job record with essential fields only."""
    job_id: str
    status: JobStatus
    created_at: str
    updated_at: str
    progress: int  # 0, 50, or 100
    parameters: JobParameters
    csv_data: Optional[str] = None  # Embedded CSV for small files
    download_url: Optional[str] = None  # S3 URL for large files
    error_message: Optional[str] = None

class JobManager:
    """Simplified job status tracking with basic S3 storage."""
    
    def __init__(self, bucket_name: str):
        """
        Initialize the job manager.
        
        Args:
            bucket_name: S3 bucket name for storing job status files
        """
        self.bucket_name = bucket_name
        self.s3_client = boto3.client('s3')
        self.job_status_prefix = 'jobs/'
        self.max_embed_size = 1024 * 1024  # 1MB limit for embedded CSV
    
    def create_job(self, parameters: Dict[str, Any]) -> str:
        """
        Create a new job with unique ID and initial status.
        
        Args:
            parameters: Job parameters dictionary
            
        Returns:
            Unique job ID string
        """
        try:
            # Generate unique job ID
            job_id = str(uuid.uuid4())
            
            # Create job parameters object
            job_params = JobParameters(
                nterms=parameters.get('nterms', 1),
                subjects=parameters.get('subjects', []),
                ranges=parameters.get('ranges', []),
                include_summer=parameters.get('include_summer', True),
                save_all=parameters.get('save_all', True),
                save_grouped=parameters.get('save_grouped', False)
            )
            
            # Create initial job record
            now = datetime.now(timezone.utc).isoformat()
            job_record = JobRecord(
                job_id=job_id,
                status=JobStatus.PENDING,
                created_at=now,
                updated_at=now,
                progress=0,  # 0% - pending
                parameters=job_params
            )
            
            # Store job record in S3
            self._store_job_record(job_record)
            
            logger.info(f"Created job {job_id}")
            return job_id
            
        except Exception as e:
            logger.error(f"Error creating job: {e}")
            raise
    
    def update_job_status(
        self, 
        job_id: str, 
        status: JobStatus, 
        error_message: Optional[str] = None
    ) -> None:
        """
        Update job status with simplified progress tracking.
        
        Args:
            job_id: Job identifier
            status: New job status
            error_message: Error message if job failed
        """
        try:
            # Retrieve existing job record
            job_record = self.get_job_status(job_id)
            if not job_record:
                raise ValueError(f"Job {job_id} not found")
            
            # Update job record
            job_record.status = status
            job_record.updated_at = datetime.now(timezone.utc).isoformat()
            
            # Set progress based on status
            if status == JobStatus.PENDING:
                job_record.progress = 0
            elif status == JobStatus.PROCESSING:
                job_record.progress = 50
            elif status == JobStatus.COMPLETED:
                job_record.progress = 100
            elif status == JobStatus.FAILED:
                job_record.progress = 0
                job_record.error_message = error_message
            
            # Store updated record
            self._store_job_record(job_record)
            
            logger.info(f"Updated job {job_id} status to {status.value}")
            
        except Exception as e:
            logger.error(f"Error updating job status for {job_id}: {e}")
            raise
    
    def complete_job(
        self, 
        job_id: str, 
        csv_content: str,
        filename: str = "enrollment_data.csv"
    ) -> None:
        """
        Mark job as completed with CSV data (embedded or S3 URL).
        
        Args:
            job_id: Job identifier
            csv_content: Generated CSV content
            filename: Name for the CSV file
        """
        try:
            # Retrieve existing job record
            job_record = self.get_job_status(job_id)
            if not job_record:
                raise ValueError(f"Job {job_id} not found")
            
            # Update job record
            job_record.status = JobStatus.COMPLETED
            job_record.updated_at = datetime.now(timezone.utc).isoformat()
            job_record.progress = 100
            
            # Check if CSV is small enough to embed
            csv_size = len(csv_content.encode('utf-8'))
            
            if csv_size <= self.max_embed_size:
                # Embed small CSV directly in response
                job_record.csv_data = csv_content
                logger.info(f"Completed job {job_id} with embedded CSV ({csv_size} bytes)")
            else:
                # Store large CSV in S3 and provide download URL
                s3_key = f"files/{job_id}_{filename}"
                
                self.s3_client.put_object(
                    Bucket=self.bucket_name,
                    Key=s3_key,
                    Body=csv_content.encode('utf-8'),
                    ContentType='text/csv',
                    ContentDisposition=f'attachment; filename="{filename}"'
                )
                
                # Generate simple download URL (valid for 24 hours)
                download_url = self.s3_client.generate_presigned_url(
                    'get_object',
                    Params={'Bucket': self.bucket_name, 'Key': s3_key},
                    ExpiresIn=86400  # 24 hours
                )
                
                job_record.download_url = download_url
                logger.info(f"Completed job {job_id} with S3 file ({csv_size} bytes)")
            
            # Store updated record
            self._store_job_record(job_record)
            
        except Exception as e:
            logger.error(f"Error completing job {job_id}: {e}")
            raise
    
    def fail_job(self, job_id: str, error_message: str) -> None:
        """
        Mark job as failed with error message.
        
        Args:
            job_id: Job identifier
            error_message: Error description
        """
        try:
            self.update_job_status(
                job_id=job_id,
                status=JobStatus.FAILED,
                error_message=error_message
            )
            
            logger.error(f"Failed job {job_id}: {error_message}")
            
        except Exception as e:
            logger.error(f"Error failing job {job_id}: {e}")
            raise
    
    def get_job_status(self, job_id: str) -> Optional[JobRecord]:
        """
        Retrieve job status from S3.
        
        Args:
            job_id: Job identifier
            
        Returns:
            JobRecord if found, None otherwise
        """
        try:
            s3_key = f"{self.job_status_prefix}{job_id}.json"
            
            response = self.s3_client.get_object(
                Bucket=self.bucket_name,
                Key=s3_key
            )
            
            job_data = json.loads(response['Body'].read().decode('utf-8'))
            
            # Convert back to JobRecord
            job_record = self._dict_to_job_record(job_data)
            
            return job_record
            
        except self.s3_client.exceptions.NoSuchKey:
            return None
        except Exception as e:
            logger.error(f"Error retrieving job status for {job_id}: {e}")
            raise
    

    
    def _store_job_record(self, job_record: JobRecord) -> None:
        """
        Store job record in S3.
        
        Args:
            job_record: JobRecord to store
        """
        try:
            s3_key = f"{self.job_status_prefix}{job_record.job_id}.json"
            
            # Convert to dictionary for JSON serialization
            job_dict = self._job_record_to_dict(job_record)
            
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=s3_key,
                Body=json.dumps(job_dict),
                ContentType='application/json'
            )
            
        except Exception as e:
            logger.error(f"Error storing job record for {job_record.job_id}: {e}")
            raise
    
    def _job_record_to_dict(self, job_record: JobRecord) -> Dict[str, Any]:
        """
        Convert JobRecord to dictionary for JSON serialization.
        
        Args:
            job_record: JobRecord to convert
            
        Returns:
            Dictionary representation
        """
        return {
            'job_id': job_record.job_id,
            'status': job_record.status.value,
            'created_at': job_record.created_at,
            'updated_at': job_record.updated_at,
            'progress': job_record.progress,
            'parameters': asdict(job_record.parameters),
            'csv_data': job_record.csv_data,
            'download_url': job_record.download_url,
            'error_message': job_record.error_message
        }
    
    def _dict_to_job_record(self, job_dict: Dict[str, Any]) -> JobRecord:
        """
        Convert dictionary to JobRecord.
        
        Args:
            job_dict: Dictionary representation
            
        Returns:
            JobRecord object
        """
        # Convert parameters
        params_dict = job_dict['parameters']
        parameters = JobParameters(
            nterms=params_dict['nterms'],
            subjects=params_dict['subjects'],
            ranges=params_dict['ranges'],
            include_summer=params_dict['include_summer'],
            save_all=params_dict['save_all'],
            save_grouped=params_dict['save_grouped']
        )
        
        return JobRecord(
            job_id=job_dict['job_id'],
            status=JobStatus(job_dict['status']),
            created_at=job_dict['created_at'],
            updated_at=job_dict['updated_at'],
            progress=job_dict['progress'],
            parameters=parameters,
            csv_data=job_dict.get('csv_data'),
            download_url=job_dict.get('download_url'),
            error_message=job_dict.get('error_message')
        )