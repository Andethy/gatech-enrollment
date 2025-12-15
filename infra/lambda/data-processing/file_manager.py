"""
File Management Module for Georgia Tech Enrollment Data Processing

This module handles CSV file storage in S3, presigned URL generation for downloads,
and file cleanup policies for the enrollment data processing system.
"""

import logging
import boto3
import os
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Tuple
from urllib.parse import quote
import pandas as pd

logger = logging.getLogger(__name__)

class FileManager:
    """Manages file storage and download URL generation for S3."""
    
    def __init__(self, bucket_name: str):
        """
        Initialize the file manager.
        
        Args:
            bucket_name: S3 bucket name for storing files
        """
        self.bucket_name = bucket_name
        self.s3_client = boto3.client('s3')
        self.generated_files_prefix = 'generated-files/'
        self.room_capacity_prefix = 'room-capacity/'
        
        # Default presigned URL expiration (24 hours)
        self.default_url_expiration = 24 * 60 * 60
    
    def store_csv_files(
        self, 
        job_id: str, 
        files: List[Dict[str, Any]], 
        timestamp: str
    ) -> List[Dict[str, Any]]:
        """
        Store CSV files in S3 with proper naming and metadata.
        
        Args:
            job_id: Job identifier for organizing files
            files: List of file data dictionaries with 'filename', 'data', 'type'
            timestamp: Timestamp string for file naming
            
        Returns:
            List of file information with S3 keys and download URLs
        """
        stored_files = []
        
        try:
            for file_data in files:
                filename = file_data['filename']
                df = file_data['data']
                file_type = file_data.get('type', 'unknown')
                
                # Generate S3 key with job organization
                s3_key = self._generate_s3_key(job_id, filename, timestamp)
                
                # Convert DataFrame to CSV
                csv_content = df.to_csv(index=False)
                csv_bytes = csv_content.encode('utf-8')
                
                # Store file in S3
                self.s3_client.put_object(
                    Bucket=self.bucket_name,
                    Key=s3_key,
                    Body=csv_bytes,
                    ContentType='text/csv',
                    ContentDisposition=f'attachment; filename="{filename}"',
                    Metadata={
                        'job-id': job_id,
                        'file-type': file_type,
                        'generated-at': timestamp,
                        'row-count': str(len(df)),
                        'column-count': str(len(df.columns))
                    },
                    ServerSideEncryption='AES256'
                )
                
                # Generate presigned download URL
                download_url = self.generate_download_url(s3_key)
                
                stored_file_info = {
                    'filename': filename,
                    's3_key': s3_key,
                    'download_url': download_url,
                    'size_bytes': len(csv_bytes),
                    'type': file_type,
                    'row_count': len(df),
                    'column_count': len(df.columns)
                }
                
                stored_files.append(stored_file_info)
                
                logger.info(f"Stored file {filename} ({len(csv_bytes)} bytes) as {s3_key}")
            
            logger.info(f"Successfully stored {len(stored_files)} files for job {job_id}")
            return stored_files
            
        except Exception as e:
            logger.error(f"Error storing CSV files for job {job_id}: {e}")
            raise
    
    def store_room_capacity_file(
        self, 
        filename: str, 
        df: pd.DataFrame,
        source_type: str = 'upload'
    ) -> Dict[str, Any]:
        """
        Store room capacity CSV file in S3.
        
        Args:
            filename: Original filename
            df: DataFrame containing room capacity data
            source_type: Source of the data ('upload', 'pdf_processing', etc.)
            
        Returns:
            File information dictionary
        """
        try:
            # Generate timestamp for versioning
            timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H%M%S")
            
            # Create versioned filename
            base_name, ext = os.path.splitext(filename)
            versioned_filename = f"{base_name}_{timestamp}{ext}"
            
            # Generate S3 key
            s3_key = f"{self.room_capacity_prefix}{versioned_filename}"
            
            # Convert DataFrame to CSV
            csv_content = df.to_csv(index=False)
            csv_bytes = csv_content.encode('utf-8')
            
            # Store file in S3
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=s3_key,
                Body=csv_bytes,
                ContentType='text/csv',
                ContentDisposition=f'attachment; filename="{versioned_filename}"',
                Metadata={
                    'source-type': source_type,
                    'original-filename': filename,
                    'generated-at': timestamp,
                    'row-count': str(len(df)),
                    'column-count': str(len(df.columns))
                },
                ServerSideEncryption='AES256'
            )
            
            # Also store as 'latest' version for easy access
            latest_key = f"{self.room_capacity_prefix}latest_{os.path.basename(filename)}"
            self.s3_client.copy_object(
                Bucket=self.bucket_name,
                CopySource={'Bucket': self.bucket_name, 'Key': s3_key},
                Key=latest_key,
                MetadataDirective='COPY'
            )
            
            # Generate download URL
            download_url = self.generate_download_url(s3_key)
            
            file_info = {
                'filename': versioned_filename,
                's3_key': s3_key,
                'download_url': download_url,
                'size_bytes': len(csv_bytes),
                'row_count': len(df),
                'column_count': len(df.columns),
                'latest_key': latest_key
            }
            
            logger.info(f"Stored room capacity file {versioned_filename} ({len(csv_bytes)} bytes)")
            return file_info
            
        except Exception as e:
            logger.error(f"Error storing room capacity file {filename}: {e}")
            raise
    
    def generate_download_url(
        self, 
        s3_key: str, 
        expiration_seconds: Optional[int] = None
    ) -> str:
        """
        Generate presigned URL for file download.
        
        Args:
            s3_key: S3 object key
            expiration_seconds: URL expiration time in seconds
            
        Returns:
            Presigned download URL
        """
        try:
            if expiration_seconds is None:
                expiration_seconds = self.default_url_expiration
            
            url = self.s3_client.generate_presigned_url(
                'get_object',
                Params={
                    'Bucket': self.bucket_name,
                    'Key': s3_key
                },
                ExpiresIn=expiration_seconds
            )
            
            logger.debug(f"Generated download URL for {s3_key} (expires in {expiration_seconds}s)")
            return url
            
        except Exception as e:
            logger.error(f"Error generating download URL for {s3_key}: {e}")
            raise
    
    def get_file_info(self, s3_key: str) -> Optional[Dict[str, Any]]:
        """
        Get file information from S3.
        
        Args:
            s3_key: S3 object key
            
        Returns:
            File information dictionary or None if not found
        """
        try:
            response = self.s3_client.head_object(
                Bucket=self.bucket_name,
                Key=s3_key
            )
            
            file_info = {
                'filename': os.path.basename(s3_key),
                's3_key': s3_key,
                'size_bytes': response['ContentLength'],
                'last_modified': response['LastModified'].isoformat(),
                'content_type': response.get('ContentType', 'application/octet-stream'),
                'metadata': response.get('Metadata', {})
            }
            
            # Generate fresh download URL
            file_info['download_url'] = self.generate_download_url(s3_key)
            
            return file_info
            
        except self.s3_client.exceptions.NoSuchKey:
            logger.warning(f"File not found: {s3_key}")
            return None
        except Exception as e:
            logger.error(f"Error getting file info for {s3_key}: {e}")
            raise
    
    def list_job_files(self, job_id: str) -> List[Dict[str, Any]]:
        """
        List all files for a specific job.
        
        Args:
            job_id: Job identifier
            
        Returns:
            List of file information dictionaries
        """
        try:
            prefix = f"{self.generated_files_prefix}{job_id}/"
            
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=prefix
            )
            
            files = []
            for obj in response.get('Contents', []):
                file_info = self.get_file_info(obj['Key'])
                if file_info:
                    files.append(file_info)
            
            logger.info(f"Found {len(files)} files for job {job_id}")
            return files
            
        except Exception as e:
            logger.error(f"Error listing files for job {job_id}: {e}")
            return []
    
    def list_room_capacity_files(self) -> List[Dict[str, Any]]:
        """
        List all room capacity files.
        
        Returns:
            List of file information dictionaries
        """
        try:
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=self.room_capacity_prefix
            )
            
            files = []
            for obj in response.get('Contents', []):
                # Skip 'latest_' files to avoid duplicates
                if 'latest_' not in obj['Key']:
                    file_info = self.get_file_info(obj['Key'])
                    if file_info:
                        files.append(file_info)
            
            # Sort by last modified (most recent first)
            files.sort(key=lambda x: x['last_modified'], reverse=True)
            
            logger.info(f"Found {len(files)} room capacity files")
            return files
            
        except Exception as e:
            logger.error(f"Error listing room capacity files: {e}")
            return []
    
    def get_latest_room_capacity_file(self, filename: str) -> Optional[Dict[str, Any]]:
        """
        Get the latest version of a room capacity file.
        
        Args:
            filename: Base filename to look for
            
        Returns:
            File information dictionary or None if not found
        """
        try:
            latest_key = f"{self.room_capacity_prefix}latest_{filename}"
            return self.get_file_info(latest_key)
            
        except Exception as e:
            logger.error(f"Error getting latest room capacity file {filename}: {e}")
            return None
    
    def cleanup_old_files(self, days: int = 30) -> Tuple[int, int]:
        """
        Clean up old generated files based on lifecycle policy.
        
        Args:
            days: Number of days to keep files
            
        Returns:
            Tuple of (generated_files_deleted, job_files_deleted)
        """
        try:
            cutoff_time = datetime.now(timezone.utc) - timedelta(days=days)
            
            # Clean up generated files
            generated_deleted = self._cleanup_prefix(
                self.generated_files_prefix, 
                cutoff_time
            )
            
            # Clean up old room capacity files (keep latest versions)
            capacity_deleted = self._cleanup_old_capacity_files(cutoff_time)
            
            logger.info(f"Cleaned up {generated_deleted} generated files and {capacity_deleted} capacity files")
            return generated_deleted, capacity_deleted
            
        except Exception as e:
            logger.error(f"Error cleaning up old files: {e}")
            return 0, 0
    
    def _generate_s3_key(self, job_id: str, filename: str, timestamp: str) -> str:
        """
        Generate S3 key for a file.
        
        Args:
            job_id: Job identifier
            filename: Original filename
            timestamp: Timestamp string
            
        Returns:
            S3 key string
        """
        # Sanitize filename for S3
        safe_filename = quote(filename, safe='.-_')
        
        # Organize by date for better S3 performance
        date_prefix = timestamp[:10]  # YYYY-MM-DD
        
        return f"{self.generated_files_prefix}{date_prefix}/{job_id}/{safe_filename}"
    
    def _cleanup_prefix(self, prefix: str, cutoff_time: datetime) -> int:
        """
        Clean up files under a specific prefix older than cutoff time.
        
        Args:
            prefix: S3 prefix to clean up
            cutoff_time: Files older than this will be deleted
            
        Returns:
            Number of files deleted
        """
        try:
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=prefix
            )
            
            deleted_count = 0
            objects_to_delete = []
            
            for obj in response.get('Contents', []):
                if obj['LastModified'].replace(tzinfo=timezone.utc) < cutoff_time:
                    objects_to_delete.append({'Key': obj['Key']})
                    
                    # Delete in batches of 1000 (S3 limit)
                    if len(objects_to_delete) >= 1000:
                        self._delete_objects_batch(objects_to_delete)
                        deleted_count += len(objects_to_delete)
                        objects_to_delete = []
            
            # Delete remaining objects
            if objects_to_delete:
                self._delete_objects_batch(objects_to_delete)
                deleted_count += len(objects_to_delete)
            
            return deleted_count
            
        except Exception as e:
            logger.error(f"Error cleaning up prefix {prefix}: {e}")
            return 0
    
    def _cleanup_old_capacity_files(self, cutoff_time: datetime) -> int:
        """
        Clean up old room capacity files, keeping the most recent versions.
        
        Args:
            cutoff_time: Files older than this will be considered for deletion
            
        Returns:
            Number of files deleted
        """
        try:
            # Get all capacity files
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=self.room_capacity_prefix
            )
            
            # Group files by base name
            file_groups = {}
            for obj in response.get('Contents', []):
                key = obj['Key']
                
                # Skip latest_ files
                if 'latest_' in key:
                    continue
                
                # Extract base filename
                filename = os.path.basename(key)
                base_name = filename.split('_')[0]  # Remove timestamp
                
                if base_name not in file_groups:
                    file_groups[base_name] = []
                
                file_groups[base_name].append({
                    'key': key,
                    'last_modified': obj['LastModified'].replace(tzinfo=timezone.utc)
                })
            
            # For each group, keep the 3 most recent files and delete older ones
            deleted_count = 0
            for base_name, files in file_groups.items():
                # Sort by last modified (newest first)
                files.sort(key=lambda x: x['last_modified'], reverse=True)
                
                # Keep the 3 most recent, delete the rest if they're older than cutoff
                files_to_delete = []
                for i, file_info in enumerate(files):
                    if i >= 3 and file_info['last_modified'] < cutoff_time:
                        files_to_delete.append({'Key': file_info['key']})
                
                if files_to_delete:
                    self._delete_objects_batch(files_to_delete)
                    deleted_count += len(files_to_delete)
            
            return deleted_count
            
        except Exception as e:
            logger.error(f"Error cleaning up old capacity files: {e}")
            return 0
    
    def _delete_objects_batch(self, objects: List[Dict[str, str]]) -> None:
        """
        Delete a batch of objects from S3.
        
        Args:
            objects: List of objects to delete with 'Key' field
        """
        try:
            if not objects:
                return
            
            self.s3_client.delete_objects(
                Bucket=self.bucket_name,
                Delete={
                    'Objects': objects,
                    'Quiet': True
                }
            )
            
            logger.debug(f"Deleted batch of {len(objects)} objects")
            
        except Exception as e:
            logger.error(f"Error deleting objects batch: {e}")
            raise
    
    def upload_initial_capacity_data(self, capacity_csv_path: str, buildings_csv_path: str) -> Dict[str, Any]:
        """
        Upload initial capacity data and building mappings to S3.
        This is a utility method for initial setup.
        
        Args:
            capacity_csv_path: Path to the capacities.csv file
            buildings_csv_path: Path to the gt-scheduler-buildings.csv file
            
        Returns:
            Dictionary with upload results
        """
        try:
            results = {}
            
            # Upload capacity data
            if os.path.exists(capacity_csv_path):
                df_capacity = pd.read_csv(capacity_csv_path)
                capacity_result = self.store_room_capacity_file(
                    filename='capacities.csv',
                    df=df_capacity,
                    source_type='initial_setup'
                )
                results['capacity_data'] = capacity_result
                logger.info(f"Uploaded capacity data: {len(df_capacity)} records")
            else:
                logger.warning(f"Capacity file not found: {capacity_csv_path}")
            
            # Upload building mappings
            if os.path.exists(buildings_csv_path):
                df_buildings = pd.read_csv(buildings_csv_path)
                buildings_result = self.store_room_capacity_file(
                    filename='gt-scheduler-buildings.csv',
                    df=df_buildings,
                    source_type='initial_setup'
                )
                results['building_mappings'] = buildings_result
                logger.info(f"Uploaded building mappings: {len(df_buildings)} records")
            else:
                logger.warning(f"Buildings file not found: {buildings_csv_path}")
            
            return results
            
        except Exception as e:
            logger.error(f"Error uploading initial capacity data: {e}")
            raise