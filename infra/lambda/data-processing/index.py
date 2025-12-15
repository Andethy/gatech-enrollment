"""
Data Processing Lambda Function for Georgia Tech Enrollment Data

This Lambda function handles enrollment data processing requests, including:
- Fetching data from GT Scheduler APIs
- Processing and filtering enrollment data
- Generating CSV reports
- Managing job status and file storage in S3
"""

import json
import logging
import os
import traceback
import uuid
import time
from datetime import datetime
from typing import Dict, Any, List, Optional
from enum import Enum
import boto3

from scheduler_client import SchedulerClient
from data_processor import DataProcessor
from job_manager import JobManager, JobStatus
from validation import validate_enrollment_parameters, normalize_subjects

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
            'lambda_function': os.getenv('AWS_LAMBDA_FUNCTION_NAME', 'data-processing'),
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

# Global processor instance for Lambda container reuse
global_processor = None

def get_processor():
    """Get or create a global DataProcessor instance with capacity data loaded."""
    global global_processor
    if global_processor is None:
        from data_processor import DataProcessor
        global_processor = DataProcessor()
        global_processor.initialize_with_capacity_data()
    return global_processor

class ErrorCategory(Enum):
    """Simplified error categories."""
    CLIENT_ERROR = "client_error"
    SERVER_ERROR = "server_error"
    TIMEOUT_ERROR = "timeout_error"

class ProcessingError(Exception):
    """Simplified exception for processing errors."""
    
    def __init__(self, message: str, category: ErrorCategory, status_code: int = 500):
        super().__init__(message)
        self.category = category
        self.status_code = status_code

def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Main handler for enrollment data processing requests.
    
    Args:
        event: API Gateway event or SQS event containing request data
        context: Lambda context object
        
    Returns:
        Dict containing HTTP response with status code and body
    """
    try:
        # Check if this is an SQS event (async processing)
        if 'Records' in event:
            return handle_sqs_processing(event, context)
        
        # Otherwise, handle as API Gateway event
        # Extract HTTP method and path
        http_method = event.get('httpMethod', '')
        path = event.get('path', '')
        
        # Route the request based on method and path
        if http_method == 'POST' and path.endswith('/enrollment/generate'):
            response = handle_enrollment_generation(event, context)
        elif http_method == 'GET' and '/jobs/' in path and path.endswith('/status'):
            response = handle_job_status(event, context)
        else:
            raise ProcessingError(
                f"Endpoint not found: {http_method} {path}",
                ErrorCategory.CLIENT_ERROR,
                404
            )
        
        return response
            
    except ProcessingError as e:
        logger.error(f"Processing error: {str(e)}")
        return create_error_response(e.status_code, str(e))
        
    except Exception as e:
        logger.error(f"System error: {str(e)}")
        return create_error_response(500, 'Internal server error')
    

def handle_sqs_processing(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Handle SQS events for async job processing.
    
    Args:
        event: SQS event containing job records
        context: Lambda context
        
    Returns:
        Dict containing batch processing results
    """
    batch_item_failures = []
    
    for record in event.get('Records', []):
        try:
            # Parse SQS message
            message_body = json.loads(record['body'])
            job_id = message_body.get('job_id')
            parameters = message_body.get('parameters', {})
            
            if not job_id:
                logger.error("No job_id found in SQS message")
                continue
            
            # Process the job
            result = handle_async_processing(job_id, parameters, context)
            
            if not result.get('success', False):
                # Add to batch failures for retry
                batch_item_failures.append({
                    'itemIdentifier': record['messageId']
                })
                
        except Exception as e:
            logger.error(f"Failed to process SQS record: {str(e)}")
            batch_item_failures.append({
                'itemIdentifier': record['messageId']
            })
    
    return {
        'batchItemFailures': batch_item_failures
    }


def handle_enrollment_generation(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Handle POST /api/v1/enrollment/generate requests.
    
    Args:
        event: API Gateway event
        context: Lambda context
        
    Returns:
        Dict containing job ID for tracking progress
    """
    job_id = None
    
    try:
        
        # Validate S3 configuration
        bucket_name = os.getenv('S3_BUCKET_NAME')
        if not bucket_name:
            raise ProcessingError(
                "S3 bucket not configured",
                ErrorCategory.SERVER_ERROR,
                500
            )
        
        # Initialize job manager
        job_manager = JobManager(bucket_name)
        
        # Parse and validate request body
        try:
            body = json.loads(event.get('body', '{}'))
        except json.JSONDecodeError:
            raise ProcessingError(
                "Invalid JSON in request body",
                ErrorCategory.CLIENT_ERROR,
                400
            )
        
        # Validate required parameters
        validation_errors = validate_enrollment_parameters(body)
        if validation_errors:
            raise ProcessingError(
                "Invalid request parameters",
                ErrorCategory.CLIENT_ERROR,
                400
            )
        
        # Create job with initial status
        job_id = job_manager.create_job(body)
        logger.info(f"Created job {job_id}")
        
        # Trigger async processing via SQS
        import boto3
        sqs_client = boto3.client('sqs')
        queue_url = os.getenv('SQS_QUEUE_URL')
        
        if not queue_url:
            raise ProcessingError(
                "SQS queue not configured",
                ErrorCategory.SERVER_ERROR,
                500
            )
        
        sqs_message = {
            'job_id': job_id,
            'parameters': body
        }
        
        try:
            sqs_client.send_message(
                QueueUrl=queue_url,
                MessageBody=json.dumps(sqs_message),
                MessageAttributes={
                    'JobId': {
                        'StringValue': job_id,
                        'DataType': 'String'
                    }
                }
            )
            logger.info(f"Queued job {job_id} for async processing")
        except Exception as e:
            logger.error(f"Failed to queue job for processing: {str(e)}")
            job_manager.fail_job(job_id, f"Failed to queue job: {str(e)}")
            raise ProcessingError(
                "Failed to queue job for processing",
                ErrorCategory.SERVER_ERROR,
                500
            )
        
        # Return immediately with job ID
        return {
            'statusCode': 202,  # Accepted - processing started
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': 'Content-Type,Authorization',
                'Access-Control-Allow-Methods': 'GET,POST,OPTIONS'
            },
            'body': json.dumps({
                'job_id': job_id,
                'status': 'pending',
                'message': 'Job submitted successfully. Use the job status endpoint to track progress.'
            })
        }
        
    except ProcessingError:
        # Fail the job if we have a job_id
        if job_id:
            try:
                job_manager.fail_job(job_id, "Job submission failed")
            except:
                pass  # Don't fail on cleanup errors
        raise
    except Exception as e:
        # Fail the job if we have a job_id
        if job_id:
            try:
                job_manager.fail_job(job_id, str(e))
            except:
                pass  # Don't fail on cleanup errors
        
        raise ProcessingError(
            f"Unexpected error: {str(e)}",
            ErrorCategory.SERVER_ERROR,
            500
        )


def handle_async_processing(job_id: str, parameters: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Handle async processing for enrollment data generation.
    
    Args:
        job_id: Job identifier
        parameters: Job parameters
        context: Lambda context
        
    Returns:
        Dict containing processing result
    """
    
    try:
        # Validate S3 configuration
        bucket_name = os.getenv('S3_BUCKET_NAME')
        if not bucket_name:
            raise ProcessingError(
                "S3 bucket not configured",
                ErrorCategory.SERVER_ERROR,
                500
            )
        
        # Initialize job manager
        job_manager = JobManager(bucket_name)
        
        # Update job status to processing
        job_manager.update_job_status(job_id, JobStatus.PROCESSING)
        
        # Extract parameters with defaults and normalize subjects
        nterms = parameters.get('nterms', 1)
        subjects = normalize_subjects(parameters.get('subjects', []))
        ranges = [tuple(r) for r in parameters.get('ranges', [])]
        include_summer = parameters.get('include_summer', True)
        save_all = parameters.get('save_all', True)
        save_grouped = parameters.get('save_grouped', False)
        
        logger.info(f"Processing enrollment data for job {job_id}")
        
        # Process the enrollment data
        try:
            processor = get_processor()
            
            # Run the async processing with timeout
            import asyncio
            
            # Set timeout based on Lambda execution time limit
            timeout_seconds = (context.get_remaining_time_in_millis() // 1000) - 30 if context else 840
            
            result = asyncio.run(asyncio.wait_for(
                processor.compile_enrollment_data(
                    nterms=nterms,
                    subjects=subjects,
                    ranges=ranges,
                    include_summer=include_summer,
                    save_all=save_all,
                    save_grouped=save_grouped
                ),
                timeout=timeout_seconds
            ))
            
        except asyncio.TimeoutError:
            job_manager.fail_job(job_id, "Data processing timed out")
            logger.error(f"Job {job_id} timed out")
            return {'success': False, 'error': 'Processing timed out'}
        except Exception as e:
            job_manager.fail_job(job_id, f"Data processing failed: {str(e)}")
            logger.error(f"Job {job_id} failed: {str(e)}")
            return {'success': False, 'error': f'Processing failed: {str(e)}'}
        
        if not result.get('success', False):
            job_manager.fail_job(job_id, "Data processing failed")
            logger.error(f"Job {job_id} failed: Data processing returned failure")
            return {'success': False, 'error': 'Data processing failed'}
        
        # Convert result to CSV
        if result.get('files') and len(result['files']) > 0:
            # For simplicity, just take the first file and convert to CSV
            first_file = result['files'][0]
            df = first_file['data']
            csv_content = df.to_csv(index=False)
            filename = first_file['filename']
        else:
            csv_content = "No data found"
            filename = "enrollment_data.csv"
        
        # Complete the job with CSV data
        job_manager.complete_job(job_id, csv_content, filename)
        
        logger.info(f"Successfully completed job {job_id}")
        
        return {
            'success': True,
            'job_id': job_id,
            'message': 'Processing completed successfully'
        }
        
    except Exception as e:
        if job_id:
            try:
                job_manager.fail_job(job_id, str(e))
            except:
                pass
        
        logger.error(f"Async processing failed for job {job_id}: {str(e)}")
        return {
            'success': False,
            'job_id': job_id,
            'error': str(e)
        }

def handle_job_status(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Handle GET /api/v1/jobs/{jobId}/status requests.
    
    Args:
        event: API Gateway event
        context: Lambda context
        
    Returns:
        Dict containing job status information
    """
    try:
        # Validate S3 configuration
        bucket_name = os.getenv('S3_BUCKET_NAME')
        if not bucket_name:
            raise ProcessingError(
                "S3 bucket not configured",
                ErrorCategory.SERVER_ERROR,
                500
            )
        
        # Initialize job manager
        job_manager = JobManager(bucket_name)
        
        # Extract and validate job ID from path parameters
        path_parameters = event.get('pathParameters', {})
        job_id = path_parameters.get('jobId')
        
        if not job_id:
            raise ProcessingError(
                "Missing job ID in path parameters",
                ErrorCategory.CLIENT_ERROR,
                400
            )
        
        # Validate job ID format (should be UUID)
        try:
            uuid.UUID(job_id)
        except ValueError:
            raise ProcessingError(
                "Invalid job ID format",
                ErrorCategory.CLIENT_ERROR,
                400
            )
        
        # Retrieve job status from S3
        job_record = job_manager.get_job_status(job_id)
        
        if not job_record:
            raise ProcessingError(
                "Job not found",
                ErrorCategory.CLIENT_ERROR,
                404
            )
        
        # Prepare response data
        response_data = {
            'job_id': job_record.job_id,
            'status': job_record.status.value,
            'progress': job_record.progress,
            'created_at': job_record.created_at,
            'updated_at': job_record.updated_at
        }
        
        # Add error message if job failed
        if job_record.error_message:
            response_data['error_message'] = job_record.error_message
        
        # Add CSV data or download URL if job completed
        if job_record.status == JobStatus.COMPLETED:
            if job_record.csv_data:
                response_data['csv_data'] = job_record.csv_data
            elif job_record.download_url:
                response_data['download_url'] = job_record.download_url
        
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': 'Content-Type,Authorization',
                'Access-Control-Allow-Methods': 'GET,POST,OPTIONS'
            },
            'body': json.dumps(response_data)
        }
        
    except ProcessingError:
        raise
    except Exception as e:
        raise ProcessingError(
            f"Unexpected error retrieving job status: {str(e)}",
            ErrorCategory.SERVER_ERROR,
            500
        )




def create_error_response(status_code: int, message: str) -> Dict[str, Any]:
    """
    Create a simple error response.
    
    Args:
        status_code: HTTP status code
        message: Error message
        
    Returns:
        Dict containing error response
    """
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type,Authorization',
            'Access-Control-Allow-Methods': 'GET,POST,OPTIONS'
        },
        'body': json.dumps({
            'error': message,
            'status_code': status_code
        })
    }


