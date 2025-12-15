import json
import logging
import os
import uuid
import time
import traceback
from datetime import datetime
from typing import Dict, Any, List, Tuple, Optional
from enum import Enum
import boto3
from botocore.exceptions import ClientError
import pdfplumber
import regex
import pandas as pd
from io import BytesIO
import base64
from pdf_parser import RoomCapacityParser

# Configure structured logging
logger = logging.getLogger()
logger.setLevel(os.getenv('LOG_LEVEL', 'INFO'))

# Add structured logging formatter
class StructuredFormatter(logging.Formatter):
    """Custom formatter for structured logging."""
    
    def format(self, record):
        log_entry = {
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'level': record.levelname,
            'message': record.getMessage(),
            'function': record.funcName,
            'line': record.lineno,
            'lambda_function': os.getenv('AWS_LAMBDA_FUNCTION_NAME', 'pdf-processing'),
            'request_id': getattr(record, 'request_id', 'unknown'),
            'correlation_id': getattr(record, 'correlation_id', 'unknown')
        }
        
        if record.exc_info:
            log_entry['exception'] = self.formatException(record.exc_info)
        
        return json.dumps(log_entry)

# Configure structured logging
handler = logging.StreamHandler()
handler.setFormatter(StructuredFormatter())
logger.handlers = [handler]

class ErrorCategory(Enum):
    """Categories of errors for proper handling and response codes."""
    VALIDATION_ERROR = "validation_error"
    PDF_PROCESSING_ERROR = "pdf_processing_error"
    STORAGE_ERROR = "storage_error"
    AUTHENTICATION_ERROR = "authentication_error"
    SYSTEM_ERROR = "system_error"
    FILE_FORMAT_ERROR = "file_format_error"

class PDFProcessingError(Exception):
    """Custom exception for PDF processing errors with categorization."""
    
    def __init__(self, message: str, category: ErrorCategory, details: Optional[Dict[str, Any]] = None, status_code: int = 500):
        super().__init__(message)
        self.category = category
        self.details = details or {}
        self.status_code = status_code
        self.correlation_id = str(uuid.uuid4())

# Initialize AWS clients with error handling
try:
    s3_client = boto3.client('s3')
    S3_BUCKET_NAME = os.getenv('S3_BUCKET_NAME')
    
    if not S3_BUCKET_NAME:
        logger.error("S3_BUCKET_NAME environment variable not set")
except Exception as e:
    logger.error(f"Failed to initialize AWS clients: {e}")
    s3_client = None

def lambda_handler(event, context):
    """
    AWS Lambda handler for PDF processing requests.
    
    Handles:
    - POST /api/v1/capacity/upload - Process uploaded PDF files
    - GET /api/v1/capacity/data - Return current capacity data
    """
    # Generate correlation ID for request tracking
    correlation_id = str(uuid.uuid4())
    request_id = context.aws_request_id if context else 'unknown'
    start_time = time.time()
    
    # Add correlation ID to all log records
    old_factory = logging.getLogRecordFactory()
    def record_factory(*args, **kwargs):
        record = old_factory(*args, **kwargs)
        record.correlation_id = correlation_id
        record.request_id = request_id
        return record
    logging.setLogRecordFactory(record_factory)
    
    try:
        # Validate system configuration
        if not s3_client:
            raise PDFProcessingError(
                "AWS S3 client not initialized",
                ErrorCategory.SYSTEM_ERROR,
                {'missing_client': 's3_client'},
                500
            )
        
        if not S3_BUCKET_NAME:
            raise PDFProcessingError(
                "S3 bucket not configured",
                ErrorCategory.SYSTEM_ERROR,
                {'missing_env_var': 'S3_BUCKET_NAME'},
                500
            )
        
        # Parse the event
        http_method = event.get('httpMethod', '')
        path = event.get('path', '')
        
        logger.info("Processing PDF processing request", extra={
            'http_method': http_method,
            'path': path,
            'correlation_id': correlation_id,
            'request_id': request_id
        })
        
        # Route requests with error handling
        if http_method == 'POST' and path.endswith('/capacity/upload'):
            response = handle_pdf_upload(event, context, correlation_id)
        elif http_method == 'GET' and path.endswith('/capacity/data'):
            response = handle_capacity_data_request(event, context, correlation_id)
        else:
            raise PDFProcessingError(
                f"Endpoint not found: {http_method} {path}",
                ErrorCategory.VALIDATION_ERROR,
                {'method': http_method, 'path': path},
                404
            )
        
        # Log successful request completion
        duration_ms = (time.time() - start_time) * 1000
        logger.info("Request completed successfully", extra={
            'endpoint': path,
            'method': http_method,
            'status_code': response['statusCode'],
            'duration_ms': duration_ms,
            'correlation_id': correlation_id
        })
        
        return response
            
    except PDFProcessingError as e:
        logger.error(f"PDF processing error: {e.message}", extra={
            'error_category': e.category.value,
            'error_details': e.details,
            'correlation_id': e.correlation_id,
            'status_code': e.status_code
        })
        
        # Log error details
        duration_ms = (time.time() - start_time) * 1000
        logger.error("Request failed", extra={
            'endpoint': event.get('path', 'unknown'),
            'method': event.get('httpMethod', 'unknown'),
            'status_code': e.status_code,
            'duration_ms': duration_ms,
            'error_category': e.category.value,
            'correlation_id': correlation_id
        })
        
        return create_error_response(e.status_code, e.message, e.details, e.correlation_id)
        
    except Exception as e:
        logger.error(f"Unhandled system error: {str(e)}", extra={
            'correlation_id': correlation_id,
            'exception_type': type(e).__name__,
            'stack_trace': traceback.format_exc()
        })
        
        # Log error details
        duration_ms = (time.time() - start_time) * 1000
        logger.error("Request failed with system error", extra={
            'endpoint': event.get('path', 'unknown'),
            'method': event.get('httpMethod', 'unknown'),
            'status_code': 500,
            'duration_ms': duration_ms,
            'error_category': 'system_error',
            'correlation_id': correlation_id
        })
        
        return create_error_response(
            500, 
            'Internal server error', 
            {'error_type': type(e).__name__}, 
            correlation_id
        )
    
    finally:
        # Restore original log record factory
        logging.setLogRecordFactory(old_factory)

def handle_pdf_upload(event: Dict[str, Any], context: Any, correlation_id: str) -> Dict[str, Any]:
    """Handle PDF file upload and processing."""
    job_id = None
    
    try:
        # Validate content type
        content_type = event.get('headers', {}).get('content-type', '')
        if not content_type.startswith('multipart/form-data'):
            raise PDFProcessingError(
                "Invalid content type for PDF upload",
                ErrorCategory.VALIDATION_ERROR,
                {'content_type': content_type, 'expected': 'multipart/form-data'},
                400
            )
        
        # Validate request body exists
        if not event.get('body'):
            raise PDFProcessingError(
                "Request body is required for file upload",
                ErrorCategory.VALIDATION_ERROR,
                {'body_present': False},
                400
            )
        
        # Extract PDF data from the request body with error handling
        try:
            pdf_data = extract_pdf_from_request(event)
        except Exception as e:
            raise PDFProcessingError(
                "Failed to extract PDF file from request",
                ErrorCategory.FILE_FORMAT_ERROR,
                {'original_error': str(e), 'error_type': type(e).__name__},
                400
            ) from e
        
        # Create job ID for tracking
        job_id = str(uuid.uuid4())
        
        # Process PDF immediately (synchronous for now, can be made async later)
        try:
            # Update job status to processing
            update_job_status(job_id, 'processing', 0.1, 'Starting PDF processing')
            
            # Parse the PDF
            parser = RoomCapacityParser()
            logger.info(f"Starting PDF parsing for job {job_id}")
            room_df = parser.parse_pdf_from_bytes(pdf_data)
            
            # Update progress
            update_job_status(job_id, 'processing', 0.5, 'PDF parsed successfully, validating data')
            
            # Validate the parsed data
            validation_results = parser.validate_parsed_data(room_df)
            if not validation_results['is_valid']:
                error_msg = f"PDF validation failed: {'; '.join(validation_results['errors'])}"
                update_job_status(job_id, 'failed', 1.0, error_msg)
                return {
                    'statusCode': 400,
                    'headers': {
                        'Content-Type': 'application/json',
                        'Access-Control-Allow-Origin': '*'
                    },
                    'body': json.dumps({
                        'job_id': job_id,
                        'error': 'Validation Failed',
                        'message': error_msg,
                        'validation_results': validation_results
                    })
                }
            
            # Update progress
            update_job_status(job_id, 'processing', 0.7, 'Validating CSV format')
            
            # Validate CSV format for system compatibility
            csv_validation = validate_csv_format(room_df)
            if not csv_validation['is_valid']:
                error_msg = f"CSV format validation failed: {'; '.join(csv_validation['errors'])}"
                update_job_status(job_id, 'failed', 1.0, error_msg)
                return {
                    'statusCode': 400,
                    'headers': {
                        'Content-Type': 'application/json',
                        'Access-Control-Allow-Origin': '*'
                    },
                    'body': json.dumps({
                        'job_id': job_id,
                        'error': 'CSV Format Validation Failed',
                        'message': error_msg,
                        'validation_results': csv_validation
                    })
                }
            
            # Update progress
            update_job_status(job_id, 'processing', 0.8, 'Generating and saving CSV file')
            
            # Generate CSV and save to S3
            csv_key = generate_and_save_csv(room_df, job_id)
            
            # Update progress
            update_job_status(job_id, 'processing', 0.9, 'Notifying system of capacity data update')
            
            # Notify system of the update
            notify_system_of_capacity_update(csv_key, job_id, validation_results['statistics'])
            
            # Create update summary
            update_summary = create_capacity_update_summary(room_df, job_id, csv_key)
            
            # Update job status to completed
            download_url = s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': S3_BUCKET_NAME, 'Key': csv_key},
                ExpiresIn=3600  # 1 hour
            )
            
            # Also provide download URL for the current capacity file
            current_download_url = s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': S3_BUCKET_NAME, 'Key': 'room-capacity/capacities.csv'},
                ExpiresIn=3600  # 1 hour
            )
            
            job_results = {
                'files': [
                    {
                        'filename': f'capacities_{pd.Timestamp.now().strftime("%Y%m%d_%H%M%S")}.csv',
                        's3_key': csv_key,
                        'download_url': download_url,
                        'size_bytes': len(room_df.to_csv(index=False).encode('utf-8')),
                        'file_type': 'timestamped_capacity_data'
                    },
                    {
                        'filename': 'capacities.csv',
                        's3_key': 'room-capacity/capacities.csv',
                        'download_url': current_download_url,
                        'size_bytes': len(room_df.to_csv(index=False).encode('utf-8')),
                        'file_type': 'current_capacity_data'
                    }
                ],
                'statistics': validation_results['statistics'],
                'warnings': validation_results['warnings'],
                'update_summary': update_summary,
                'system_updated': True
            }
            
            update_job_status(job_id, 'completed', 1.0, 'PDF processing completed successfully', job_results)
            
            return {
                'statusCode': 200,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({
                    'job_id': job_id,
                    'status': 'completed',
                    'message': 'PDF processed successfully',
                    'results': job_results
                })
            }
            
        except Exception as e:
            error_msg = f"PDF processing failed: {str(e)}"
            logger.error(error_msg, exc_info=True)
            update_job_status(job_id, 'failed', 1.0, error_msg)
            
            return {
                'statusCode': 500,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({
                    'job_id': job_id,
                    'error': 'Processing Failed',
                    'message': error_msg
                })
            }
        
    except Exception as e:
        logger.error(f"Error in handle_pdf_upload: {str(e)}", exc_info=True)
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'error': 'Internal Server Error',
                'message': 'Failed to process PDF upload'
            })
        }

def handle_capacity_data_request(event: Dict[str, Any], context: Any, correlation_id: str) -> Dict[str, Any]:
    """Handle request for current room capacity data."""
    try:
        # Check query parameters for format preference
        query_params = event.get('queryStringParameters') or {}
        format_param = query_params.get('format', 'json').lower()
        
        # Check if capacity data exists in S3
        try:
            response = s3_client.get_object(
                Bucket=S3_BUCKET_NAME,
                Key='room-capacity/capacities.csv'
            )
            
            # If CSV format is requested, return the file directly
            if format_param == 'csv':
                csv_content = response['Body'].read().decode('utf-8')
                return {
                    'statusCode': 200,
                    'headers': {
                        'Content-Type': 'text/csv',
                        'Content-Disposition': 'attachment; filename="capacities.csv"',
                        'Access-Control-Allow-Origin': '*'
                    },
                    'body': csv_content
                }
            
            # Default JSON response with download URL and metadata
            download_url = s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': S3_BUCKET_NAME, 'Key': 'room-capacity/capacities.csv'},
                ExpiresIn=3600  # 1 hour
            )
            
            # Parse CSV to get summary statistics for JSON response
            csv_content = response['Body'].read().decode('utf-8')
            try:
                import io
                df = pd.read_csv(io.StringIO(csv_content))
                statistics = {
                    'total_rooms': len(df),
                    'unique_buildings': df['Building Code'].nunique() if 'Building Code' in df.columns else 0,
                    'capacity_range': {
                        'min': int(df['Room Capacity'].min()) if 'Room Capacity' in df.columns else 0,
                        'max': int(df['Room Capacity'].max()) if 'Room Capacity' in df.columns else 0
                    },
                    'total_capacity': int(df['Room Capacity'].sum()) if 'Room Capacity' in df.columns else 0
                }
            except Exception as stats_error:
                logger.warning(f"Failed to generate statistics: {stats_error}")
                statistics = {}
            
            return {
                'statusCode': 200,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*',
                    'Cache-Control': 'public, max-age=300'  # Cache for 5 minutes
                },
                'body': json.dumps({
                    'download_url': download_url,
                    'filename': 'capacities.csv',
                    'last_modified': response['LastModified'].isoformat(),
                    'size_bytes': response['ContentLength'],
                    'format_options': {
                        'csv_direct': f"{event.get('requestContext', {}).get('domainName', '')}{event.get('path', '')}?format=csv",
                        'json_metadata': f"{event.get('requestContext', {}).get('domainName', '')}{event.get('path', '')}?format=json"
                    },
                    'statistics': statistics
                })
            }
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                return {
                    'statusCode': 404,
                    'headers': {
                        'Content-Type': 'application/json',
                        'Access-Control-Allow-Origin': '*'
                    },
                    'body': json.dumps({
                        'error': 'Not Found',
                        'message': 'Room capacity data not available. Upload a PDF file to generate capacity data.',
                        'upload_endpoint': '/api/v1/capacity/upload'
                    })
                }
            else:
                raise e
                
    except Exception as e:
        logger.error(f"Error in handle_capacity_data_request: {str(e)}", exc_info=True)
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'error': 'Internal Server Error',
                'message': 'Failed to retrieve capacity data'
            })
        }

def extract_pdf_from_request(event: Dict[str, Any]) -> bytes:
    """
    Extract PDF data from API Gateway multipart form request.
    
    Args:
        event: API Gateway event containing the multipart form data
        
    Returns:
        bytes: PDF file content
        
    Raises:
        Exception: If PDF extraction fails
    """
    try:
        # Get the request body
        body = event.get('body', '')
        is_base64_encoded = event.get('isBase64Encoded', False)
        
        if is_base64_encoded:
            body_bytes = base64.b64decode(body)
        else:
            body_bytes = body.encode('utf-8')
        
        # Parse multipart form data
        content_type = event.get('headers', {}).get('content-type', '')
        if 'boundary=' in content_type:
            boundary = content_type.split('boundary=')[1].strip()
            pdf_data = parse_multipart_form_data(body_bytes, boundary)
        else:
            # Fallback: assume the entire body is the PDF content
            pdf_data = body_bytes
        
        # Basic validation - check if it looks like a PDF
        if not pdf_data.startswith(b'%PDF'):
            raise ValueError("Uploaded file does not appear to be a valid PDF")
        
        # Additional PDF validation
        if len(pdf_data) < 100:  # PDFs should be at least 100 bytes
            raise ValueError("File too small to be a valid PDF")
        
        if len(pdf_data) > 50 * 1024 * 1024:  # 50MB limit
            raise ValueError("PDF file too large (maximum 50MB allowed)")
        
        logger.info(f"Extracted PDF data: {len(pdf_data)} bytes")
        return pdf_data
        
    except Exception as e:
        logger.error(f"Failed to extract PDF from request: {str(e)}")
        raise Exception(f"PDF extraction failed: {str(e)}")

def parse_multipart_form_data(body_bytes: bytes, boundary: str) -> bytes:
    """
    Parse multipart form data to extract PDF file content.
    
    Args:
        body_bytes: Raw request body bytes
        boundary: Multipart boundary string
        
    Returns:
        bytes: PDF file content
        
    Raises:
        Exception: If parsing fails
    """
    try:
        boundary_bytes = f'--{boundary}'.encode('utf-8')
        parts = body_bytes.split(boundary_bytes)
        
        for part in parts:
            if b'Content-Type: application/pdf' in part or b'filename=' in part:
                # Find the start of file content (after double CRLF)
                content_start = part.find(b'\r\n\r\n')
                if content_start != -1:
                    file_content = part[content_start + 4:]
                    # Remove trailing boundary markers
                    if file_content.endswith(b'\r\n'):
                        file_content = file_content[:-2]
                    if file_content.startswith(b'%PDF'):
                        return file_content
        
        # If no PDF part found, try to find any file content
        for part in parts:
            if b'Content-Disposition: form-data' in part and b'filename=' in part:
                content_start = part.find(b'\r\n\r\n')
                if content_start != -1:
                    file_content = part[content_start + 4:]
                    if file_content.endswith(b'\r\n'):
                        file_content = file_content[:-2]
                    if file_content.startswith(b'%PDF'):
                        return file_content
        
        raise ValueError("No PDF file found in multipart form data")
        
    except Exception as e:
        logger.error(f"Error parsing multipart form data: {str(e)}")
        raise Exception(f"Multipart parsing failed: {str(e)}")

def update_job_status(job_id: str, status: str, progress: float, message: str = None, results: Dict[str, Any] = None):
    """
    Update job status in S3.
    
    Args:
        job_id: Unique job identifier
        status: Job status (pending, processing, completed, failed)
        progress: Progress value between 0.0 and 1.0
        message: Optional status message
        results: Optional results data for completed jobs
    """
    try:
        # Get existing job status if it exists
        try:
            response = s3_client.get_object(
                Bucket=S3_BUCKET_NAME,
                Key=f'job-status/{job_id}.json'
            )
            job_status = json.loads(response['Body'].read().decode('utf-8'))
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                # Create new job status
                job_status = {
                    'job_id': job_id,
                    'job_type': 'pdf_processing',
                    'created_at': pd.Timestamp.now().isoformat(),
                    'parameters': {},
                    'results': {}
                }
            else:
                raise e
        
        # Update job status
        job_status.update({
            'status': status,
            'progress': progress,
            'updated_at': pd.Timestamp.now().isoformat()
        })
        
        if message:
            job_status['status_message'] = message
        
        if status == 'failed' and message:
            job_status['error_message'] = message
        
        if results:
            job_status['results'] = results
        
        # Save updated status to S3
        s3_client.put_object(
            Bucket=S3_BUCKET_NAME,
            Key=f'job-status/{job_id}.json',
            Body=json.dumps(job_status),
            ContentType='application/json'
        )
        
        logger.info(f"Updated job {job_id} status to {status} (progress: {progress:.1%})")
        
    except Exception as e:
        logger.error(f"Failed to update job status for {job_id}: {str(e)}")
        # Don't raise exception here to avoid breaking the main processing flow

def generate_and_save_csv(room_df: pd.DataFrame, job_id: str) -> str:
    """
    Generate CSV from room capacity DataFrame and save to S3.
    
    This function:
    1. Validates the DataFrame structure
    2. Sorts the data for consistent output
    3. Generates CSV with proper formatting
    4. Saves both timestamped and current versions to S3
    5. Updates system to use new capacity data
    
    Args:
        room_df: DataFrame containing room capacity data
        job_id: Job ID for tracking
        
    Returns:
        str: S3 key where the CSV was saved
        
    Raises:
        Exception: If CSV generation or S3 upload fails
    """
    try:
        # Validate DataFrame structure
        required_columns = ["Building Code", "Room", "Room Capacity"]
        if not all(col in room_df.columns for col in required_columns):
            raise ValueError(f"DataFrame missing required columns. Expected: {required_columns}, Got: {list(room_df.columns)}")
        
        if room_df.empty:
            raise ValueError("Cannot generate CSV from empty DataFrame")
        
        # Sort data for consistent output (by building code, then room)
        sorted_df = room_df.sort_values(['Building Code', 'Room']).reset_index(drop=True)
        
        # Ensure proper data types
        sorted_df['Building Code'] = sorted_df['Building Code'].astype(str)
        sorted_df['Room'] = sorted_df['Room'].astype(str)
        sorted_df['Room Capacity'] = sorted_df['Room Capacity'].astype(int)
        
        # Generate CSV content with proper formatting
        csv_content = sorted_df.to_csv(index=False, encoding='utf-8')
        csv_bytes = csv_content.encode('utf-8')
        
        # Generate S3 key with timestamp
        timestamp = pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')
        csv_key = f'room-capacity/capacities_{timestamp}_{job_id}.csv'
        
        # Prepare metadata
        metadata = {
            'job_id': job_id,
            'generated_at': pd.Timestamp.now().isoformat(),
            'record_count': str(len(sorted_df)),
            'unique_buildings': str(sorted_df['Building Code'].nunique()),
            'capacity_range': f"{sorted_df['Room Capacity'].min()}-{sorted_df['Room Capacity'].max()}",
            'total_capacity': str(sorted_df['Room Capacity'].sum())
        }
        
        # Upload timestamped version to S3
        s3_client.put_object(
            Bucket=S3_BUCKET_NAME,
            Key=csv_key,
            Body=csv_bytes,
            ContentType='text/csv',
            Metadata=metadata
        )
        
        # Also save as the current/latest capacity file (this updates the system to use new data)
        s3_client.put_object(
            Bucket=S3_BUCKET_NAME,
            Key='room-capacity/capacities.csv',
            Body=csv_bytes,
            ContentType='text/csv',
            Metadata=metadata
        )
        
        # Create a backup of the previous version if it exists
        try:
            # Check if current file exists
            s3_client.head_object(Bucket=S3_BUCKET_NAME, Key='room-capacity/capacities.csv')
            
            # Copy current to backup before overwriting
            backup_key = f'room-capacity/backups/capacities_backup_{timestamp}.csv'
            s3_client.copy_object(
                Bucket=S3_BUCKET_NAME,
                CopySource={'Bucket': S3_BUCKET_NAME, 'Key': 'room-capacity/capacities.csv'},
                Key=backup_key
            )
            logger.info(f"Created backup of previous capacity data: {backup_key}")
            
        except ClientError as e:
            if e.response['Error']['Code'] != 'NoSuchKey':
                logger.warning(f"Failed to create backup: {str(e)}")
            # Continue processing even if backup fails
        
        # Log success with statistics
        logger.info(f"Successfully generated and saved capacity CSV:")
        logger.info(f"  - Records: {len(sorted_df)}")
        logger.info(f"  - Buildings: {sorted_df['Building Code'].nunique()}")
        logger.info(f"  - Capacity range: {sorted_df['Room Capacity'].min()}-{sorted_df['Room Capacity'].max()}")
        logger.info(f"  - Total capacity: {sorted_df['Room Capacity'].sum():,}")
        logger.info(f"  - S3 key: {csv_key}")
        
        return csv_key
        
    except Exception as e:
        logger.error(f"Failed to generate and save CSV: {str(e)}", exc_info=True)
        raise Exception(f"CSV generation failed: {str(e)}")

def validate_csv_format(room_df: pd.DataFrame) -> Dict[str, Any]:
    """
    Validate that the CSV format matches what the enrollment system expects.
    
    Args:
        room_df: DataFrame containing room capacity data
        
    Returns:
        Dict[str, Any]: Validation results
    """
    validation_results = {
        'is_valid': True,
        'errors': [],
        'warnings': [],
        'format_info': {}
    }
    
    try:
        # Check required columns and their order
        expected_columns = ["Building Code", "Room", "Room Capacity"]
        if list(room_df.columns) != expected_columns:
            validation_results['errors'].append(
                f"Column mismatch. Expected: {expected_columns}, Got: {list(room_df.columns)}"
            )
            validation_results['is_valid'] = False
        
        # Check data types
        if 'Room Capacity' in room_df.columns:
            non_numeric = room_df[~pd.to_numeric(room_df['Room Capacity'], errors='coerce').notna()]
            if not non_numeric.empty:
                validation_results['errors'].append(
                    f"Non-numeric capacity values found: {non_numeric['Room Capacity'].unique()}"
                )
                validation_results['is_valid'] = False
        
        # Check for empty or null building codes
        if 'Building Code' in room_df.columns:
            empty_buildings = room_df[room_df['Building Code'].isna() | (room_df['Building Code'] == '')]
            if not empty_buildings.empty:
                validation_results['errors'].append(f"Found {len(empty_buildings)} rows with empty building codes")
                validation_results['is_valid'] = False
        
        # Check for empty or null room numbers
        if 'Room' in room_df.columns:
            empty_rooms = room_df[room_df['Room'].isna() | (room_df['Room'] == '')]
            if not empty_rooms.empty:
                validation_results['errors'].append(f"Found {len(empty_rooms)} rows with empty room numbers")
                validation_results['is_valid'] = False
        
        # Format information for logging
        validation_results['format_info'] = {
            'total_records': len(room_df),
            'columns': list(room_df.columns),
            'sample_data': room_df.head(3).to_dict('records') if not room_df.empty else []
        }
        
        logger.info(f"CSV format validation completed: {'PASSED' if validation_results['is_valid'] else 'FAILED'}")
        
    except Exception as e:
        validation_results['is_valid'] = False
        validation_results['errors'].append(f"Validation error: {str(e)}")
        logger.error(f"Error during CSV format validation: {str(e)}")
    
    return validation_results

def notify_system_of_capacity_update(csv_key: str, job_id: str, statistics: Dict[str, Any]):
    """
    Notify the system that new capacity data is available.
    This could trigger cache invalidation or other system updates.
    
    Args:
        csv_key: S3 key of the new capacity file
        job_id: Job ID that generated the update
        statistics: Statistics about the new data
    """
    try:
        # Create a notification record in S3
        notification = {
            'event_type': 'capacity_data_updated',
            'timestamp': pd.Timestamp.now().isoformat(),
            'job_id': job_id,
            'csv_key': csv_key,
            'statistics': statistics,
            'notification_id': str(uuid.uuid4())
        }
        
        notification_key = f'notifications/capacity_updates/{pd.Timestamp.now().strftime("%Y%m%d")}/{job_id}.json'
        
        s3_client.put_object(
            Bucket=S3_BUCKET_NAME,
            Key=notification_key,
            Body=json.dumps(notification),
            ContentType='application/json'
        )
        
        logger.info(f"Created capacity update notification: {notification_key}")
        
        # In a more complex system, this could:
        # - Send SNS notifications
        # - Trigger Lambda functions to invalidate caches
        # - Update database records
        # - Send webhooks to other services
        
    except Exception as e:
        logger.warning(f"Failed to create capacity update notification: {str(e)}")
        # Don't fail the main process if notification fails
def create_capacity_update_summary(room_df: pd.DataFrame, job_id: str, csv_key: str) -> Dict[str, Any]:
    """
    Create a summary of the capacity data update for reporting and auditing.
    
    Args:
        room_df: DataFrame containing the new capacity data
        job_id: Job ID that processed the update
        csv_key: S3 key where the CSV was saved
        
    Returns:
        Dict[str, Any]: Summary information
    """
    try:
        summary = {
            'update_id': job_id,
            'timestamp': pd.Timestamp.now().isoformat(),
            'csv_location': csv_key,
            'data_summary': {
                'total_rooms': len(room_df),
                'unique_buildings': room_df['Building Code'].nunique(),
                'building_list': sorted(room_df['Building Code'].unique().tolist()),
                'capacity_statistics': {
                    'min_capacity': int(room_df['Room Capacity'].min()),
                    'max_capacity': int(room_df['Room Capacity'].max()),
                    'mean_capacity': float(room_df['Room Capacity'].mean()),
                    'median_capacity': float(room_df['Room Capacity'].median()),
                    'total_capacity': int(room_df['Room Capacity'].sum())
                },
                'rooms_by_building': room_df.groupby('Building Code').size().to_dict()
            },
            'processing_info': {
                'source': 'pdf_upload',
                'processor_version': '1.0',
                'lambda_function': os.getenv('AWS_LAMBDA_FUNCTION_NAME', 'unknown')
            }
        }
        
        # Save summary to S3 for auditing
        summary_key = f'capacity-updates/summaries/{pd.Timestamp.now().strftime("%Y/%m/%d")}/{job_id}_summary.json'
        s3_client.put_object(
            Bucket=S3_BUCKET_NAME,
            Key=summary_key,
            Body=json.dumps(summary, indent=2),
            ContentType='application/json'
        )
        
        logger.info(f"Created capacity update summary: {summary_key}")
        return summary
        
    except Exception as e:
        logger.error(f"Failed to create capacity update summary: {str(e)}")
        return {
            'error': f"Summary creation failed: {str(e)}",
            'update_id': job_id,
            'timestamp': pd.Timestamp.now().isoformat()
        }

def create_error_response(
    status_code: int, 
    message: str, 
    details: Optional[Dict[str, Any]] = None, 
    correlation_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Create a standardized error response with enhanced error information.
    
    Args:
        status_code: HTTP status code
        message: Error message
        details: Optional error details dictionary
        correlation_id: Optional correlation ID for request tracking
        
    Returns:
        Dict containing error response
    """
    error_body = {
        'error': message,
        'status_code': status_code,
        'timestamp': datetime.utcnow().isoformat() + 'Z'
    }
    
    if details:
        error_body['details'] = details
    
    if correlation_id:
        error_body['correlation_id'] = correlation_id
    
    # Add helpful error codes for common issues
    error_codes = {
        400: 'BAD_REQUEST',
        401: 'UNAUTHORIZED',
        403: 'FORBIDDEN',
        404: 'NOT_FOUND',
        413: 'PAYLOAD_TOO_LARGE',
        415: 'UNSUPPORTED_MEDIA_TYPE',
        429: 'TOO_MANY_REQUESTS',
        500: 'INTERNAL_SERVER_ERROR',
        502: 'BAD_GATEWAY',
        503: 'SERVICE_UNAVAILABLE',
        504: 'GATEWAY_TIMEOUT'
    }
    
    error_body['error_code'] = error_codes.get(status_code, 'UNKNOWN_ERROR')
    
    headers = {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'Content-Type,Authorization',
        'Access-Control-Allow-Methods': 'GET,POST,OPTIONS'
    }
    
    if correlation_id:
        headers['X-Correlation-ID'] = correlation_id
    
    return {
        'statusCode': status_code,
        'headers': headers,
        'body': json.dumps(error_body)
    }