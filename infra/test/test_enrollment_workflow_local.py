"""
Local unit tests for the enrollment data workflow.

Tests the Lambda function directly without requiring deployed infrastructure.
This validates the core workflow logic locally.

Validates core workflow logic locally.
"""

import json
import os
import sys
import uuid
import pytest
from unittest.mock import Mock, patch, MagicMock
from typing import Dict, Any

# Add lambda directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'lambda', 'data-processing'))

# Import the Lambda function
from index import lambda_handler, handle_enrollment_generation, handle_job_status

class TestEnrollmentWorkflowLocal:
    """Local unit tests for enrollment data workflow."""
    
    def setup_method(self):
        """Set up test environment for each test."""
        # Mock environment variables
        os.environ['S3_BUCKET_NAME'] = 'test-bucket'
        os.environ['LOG_LEVEL'] = 'INFO'
    
    def test_enrollment_generation_request_structure(self):
        """Test that enrollment generation requests are structured correctly."""
        # Create a mock event for enrollment generation
        event = {
            'httpMethod': 'POST',
            'path': '/api/v1/enrollment/generate',
            'body': json.dumps({
                'nterms': 1,
                'subjects': ['CS'],
                'ranges': [[1000, 1999]],
                'include_summer': False,
                'save_all': True,
                'save_grouped': False
            }),
            'pathParameters': None
        }
        
        context = Mock()
        context.aws_request_id = 'test-request-id'
        context.get_remaining_time_in_millis = Mock(return_value=900000)  # 15 minutes
        
        # Mock all the dependencies
        with patch('index.JobManager') as mock_job_manager, \
             patch('index.FileManager') as mock_file_manager, \
             patch('index.get_processor') as mock_get_processor:
            
            # Set up mocks
            mock_job_manager_instance = Mock()
            mock_job_manager.return_value = mock_job_manager_instance
            mock_job_manager_instance.create_job.return_value = 'test-job-id'
            mock_job_manager_instance.update_job_status.return_value = None
            mock_job_manager_instance.complete_job.return_value = None
            
            mock_file_manager_instance = Mock()
            mock_file_manager.return_value = mock_file_manager_instance
            mock_file_manager_instance.store_csv_files.return_value = [
                {
                    'filename': 'test_enrollment_data.csv',
                    's3_key': 'jobs/test-job-id/test_enrollment_data.csv',
                    'size_bytes': 1024,
                    'file_type': 'ungrouped'
                }
            ]
            
            mock_processor = Mock()
            mock_get_processor.return_value = mock_processor
            
            # Mock the async processing result
            async def mock_compile_data(**kwargs):
                return {
                    'success': True,
                    'files': [{'filename': 'test_data.csv', 'content': 'test,data\n1,2'}],
                    'terms_processed': 1,
                    'last_updated': '2025-01-01-1200'
                }
            
            mock_processor.compile_enrollment_data = mock_compile_data
            
            # Call the handler
            response = lambda_handler(event, context)
            
            # Validate response structure
            assert response['statusCode'] == 202
            assert 'body' in response
            
            response_body = json.loads(response['body'])
            assert 'job_id' in response_body
            assert response_body['status'] == 'completed'
            assert 'correlation_id' in response_body
            
            # Verify mocks were called correctly
            mock_job_manager_instance.create_job.assert_called_once()
            mock_job_manager_instance.update_job_status.assert_called()
            mock_job_manager_instance.complete_job.assert_called_once()
    
    def test_job_status_request_structure(self):
        """Test that job status requests return proper structure."""
        # Create a mock event for job status
        job_id = str(uuid.uuid4())
        event = {
            'httpMethod': 'GET',
            'path': f'/api/v1/jobs/{job_id}/status',
            'pathParameters': {'jobId': job_id}
        }
        
        context = Mock()
        context.aws_request_id = 'test-request-id'
        
        # Mock the job manager
        with patch('index.JobManager') as mock_job_manager:
            mock_job_manager_instance = Mock()
            mock_job_manager.return_value = mock_job_manager_instance
            
            # Create a mock job record
            mock_job_record = Mock()
            mock_job_record.job_id = job_id
            mock_job_record.status.value = 'completed'
            mock_job_record.progress = 1.0
            mock_job_record.created_at = '2025-01-01T12:00:00Z'
            mock_job_record.updated_at = '2025-01-01T12:05:00Z'
            mock_job_record.error_message = None
            mock_job_record.terms_processed = 1
            
            # Mock parameters
            mock_parameters = Mock()
            mock_parameters.nterms = 1
            mock_parameters.subjects = ['CS']
            mock_parameters.ranges = [[1000, 1999]]
            mock_parameters.include_summer = False

            mock_parameters.save_all = True
            mock_parameters.save_grouped = False
            mock_job_record.parameters = mock_parameters
            
            # Mock results with files
            mock_file_info = Mock()
            mock_file_info.filename = 'test_enrollment_data.csv'
            mock_file_info.s3_key = 'jobs/test-job-id/test_enrollment_data.csv'
            mock_file_info.size_bytes = 1024
            mock_file_info.file_type = 'ungrouped'
            
            mock_job_record.results = {'files': [mock_file_info]}
            
            mock_job_manager_instance.get_job_status.return_value = mock_job_record
            
            # Mock file manager for download URLs
            with patch('index.FileManager') as mock_file_manager:
                mock_file_manager_instance = Mock()
                mock_file_manager.return_value = mock_file_manager_instance
                mock_file_manager_instance.generate_download_url.return_value = 'https://test-download-url.com'
                
                # Call the handler
                response = lambda_handler(event, context)
                
                # Validate response structure
                assert response['statusCode'] == 200
                assert 'body' in response
                
                response_body = json.loads(response['body'])
                
                # Validate required fields
                assert response_body['job_id'] == job_id
                assert response_body['status'] == 'completed'
                assert response_body['progress'] == 1.0
                assert 'created_at' in response_body
                assert 'updated_at' in response_body
                assert 'parameters' in response_body
                assert 'files' in response_body
                assert 'correlation_id' in response_body
                
                # Validate parameters structure
                params = response_body['parameters']
                assert params['nterms'] == 1
                assert params['subjects'] == ['CS']
                assert params['ranges'] == [[1000, 1999]]
                
                # Validate files structure
                files = response_body['files']
                assert len(files) == 1
                file_info = files[0]
                assert 'filename' in file_info
                assert 'download_url' in file_info
                assert 'size_bytes' in file_info
                assert 'file_type' in file_info
    
    def test_parameter_validation(self):
        """Test parameter validation for enrollment requests."""
        context = Mock()
        context.aws_request_id = 'test-request-id'
        
        # Test invalid parameters
        invalid_test_cases = [
            # Missing body
            {
                'httpMethod': 'POST',
                'path': '/api/v1/enrollment/generate',
                'body': None
            },
            # Invalid JSON
            {
                'httpMethod': 'POST',
                'path': '/api/v1/enrollment/generate',
                'body': 'invalid-json'
            },
            # Missing required fields
            {
                'httpMethod': 'POST',
                'path': '/api/v1/enrollment/generate',
                'body': json.dumps({})
            },
            # Invalid nterms
            {
                'httpMethod': 'POST',
                'path': '/api/v1/enrollment/generate',
                'body': json.dumps({
                    'nterms': 0,
                    'subjects': ['CS']
                })
            }
        ]
        
        for event in invalid_test_cases:
            response = lambda_handler(event, context)
            
            # Should return error status
            assert response['statusCode'] >= 400
            assert 'body' in response
            
            response_body = json.loads(response['body'])
            assert 'error' in response_body
    
    def test_job_not_found_handling(self):
        """Test handling of non-existent job IDs."""
        # Create event for non-existent job
        fake_job_id = str(uuid.uuid4())
        event = {
            'httpMethod': 'GET',
            'path': f'/api/v1/jobs/{fake_job_id}/status',
            'pathParameters': {'jobId': fake_job_id}
        }
        
        context = Mock()
        context.aws_request_id = 'test-request-id'
        
        # Mock job manager to return None (job not found)
        with patch('index.JobManager') as mock_job_manager:
            mock_job_manager_instance = Mock()
            mock_job_manager.return_value = mock_job_manager_instance
            mock_job_manager_instance.get_job_status.return_value = None
            
            response = lambda_handler(event, context)
            
            # Should return 404
            assert response['statusCode'] == 404
            response_body = json.loads(response['body'])
            assert 'error' in response_body
            assert 'not found' in response_body['error'].lower()
    
    def test_invalid_job_id_format(self):
        """Test handling of invalid job ID formats."""
        # Create event with invalid job ID
        event = {
            'httpMethod': 'GET',
            'path': '/api/v1/jobs/invalid-job-id/status',
            'pathParameters': {'jobId': 'invalid-job-id'}
        }
        
        context = Mock()
        context.aws_request_id = 'test-request-id'
        
        response = lambda_handler(event, context)
        
        # Should return 400 for invalid format
        assert response['statusCode'] == 400
        response_body = json.loads(response['body'])
        assert 'error' in response_body
        assert 'invalid' in response_body['error'].lower()
    
    def test_unsupported_endpoint(self):
        """Test handling of unsupported endpoints."""
        event = {
            'httpMethod': 'GET',
            'path': '/api/v1/unsupported/endpoint'
        }
        
        context = Mock()
        context.aws_request_id = 'test-request-id'
        
        response = lambda_handler(event, context)
        
        # Should return 404
        assert response['statusCode'] == 404
        response_body = json.loads(response['body'])
        assert 'error' in response_body
        assert 'not found' in response_body['error'].lower()
    
    def test_error_response_structure(self):
        """Test that error responses have consistent structure."""
        event = {
            'httpMethod': 'POST',
            'path': '/api/v1/enrollment/generate',
            'body': 'invalid-json'
        }
        
        context = Mock()
        context.aws_request_id = 'test-request-id'
        
        response = lambda_handler(event, context)
        
        # Validate error response structure
        assert 'statusCode' in response
        assert 'headers' in response
        assert 'body' in response
        
        # Validate headers
        headers = response['headers']
        assert 'Content-Type' in headers
        assert 'Access-Control-Allow-Origin' in headers
        assert 'X-Correlation-ID' in headers
        
        # Validate error body structure
        response_body = json.loads(response['body'])
        assert 'error' in response_body
        assert 'status_code' in response_body
        assert 'timestamp' in response_body
        assert 'error_code' in response_body
        assert 'correlation_id' in response_body
    
    def test_correlation_id_tracking(self):
        """Test that correlation IDs are properly tracked."""
        event = {
            'httpMethod': 'POST',
            'path': '/api/v1/enrollment/generate',
            'body': json.dumps({
                'nterms': 1,
                'subjects': ['CS'],
                'ranges': [[1000, 1999]]
            })
        }
        
        context = Mock()
        context.aws_request_id = 'test-request-id'
        context.get_remaining_time_in_millis.return_value = 900000  # 15 minutes in milliseconds
        
        with patch('index.JobManager') as mock_job_manager_class, \
             patch('index.FileManager') as mock_file_manager_class, \
             patch('index.get_processor') as mock_get_processor:
            
            # Mock JobManager
            mock_job_manager = Mock()
            mock_job_manager_class.return_value = mock_job_manager
            mock_job_manager.create_job.return_value = 'test-job-id'
            mock_job_manager.update_job_status.return_value = None
            mock_job_manager.complete_job.return_value = None
            
            # Mock FileManager
            mock_file_manager = Mock()
            mock_file_manager_class.return_value = mock_file_manager
            mock_file_manager.store_csv_files.return_value = [
                {'filename': 'test.csv', 's3_key': 'test-key', 'size_bytes': 1024, 'file_type': 'csv'}
            ]
            
            # Mock processor with async method
            mock_processor = Mock()
            mock_get_processor.return_value = mock_processor
            
            # Create a proper async mock
            async def mock_compile_enrollment_data(*args, **kwargs):
                return {
                    'success': True,
                    'files': [{'filename': 'test.csv', 'content': 'test,data\n1,2'}],
                    'terms_processed': 1,
                    'last_updated': '2024-01-01-1200'
                }
            
            mock_processor.compile_enrollment_data = mock_compile_enrollment_data
            
            response = lambda_handler(event, context)
            
            # Should have correlation ID in headers and body
            assert 'X-Correlation-ID' in response['headers']
            
            response_body = json.loads(response['body'])
            assert 'correlation_id' in response_body
            
            # Correlation IDs should match
            header_correlation_id = response['headers']['X-Correlation-ID']
            body_correlation_id = response_body['correlation_id']
            assert header_correlation_id == body_correlation_id


def run_local_tests():
    """Run local tests manually."""
    print("Running local enrollment workflow tests...")
    
    test_instance = TestEnrollmentWorkflowLocal()
    
    try:
        print("\n1. Testing enrollment generation request structure...")
        test_instance.setup_method()
        test_instance.test_enrollment_generation_request_structure()
        print("✓ Enrollment generation structure test passed")
        
        print("\n2. Testing job status request structure...")
        test_instance.setup_method()
        test_instance.test_job_status_request_structure()
        print("✓ Job status structure test passed")
        
        print("\n3. Testing parameter validation...")
        test_instance.setup_method()
        test_instance.test_parameter_validation()
        print("✓ Parameter validation test passed")
        
        print("\n4. Testing job not found handling...")
        test_instance.setup_method()
        test_instance.test_job_not_found_handling()
        print("✓ Job not found handling test passed")
        
        print("\n5. Testing invalid job ID format...")
        test_instance.setup_method()
        test_instance.test_invalid_job_id_format()
        print("✓ Invalid job ID format test passed")
        
        print("\n6. Testing unsupported endpoint...")
        test_instance.setup_method()
        test_instance.test_unsupported_endpoint()
        print("✓ Unsupported endpoint test passed")
        
        print("\n7. Testing error response structure...")
        test_instance.setup_method()
        test_instance.test_error_response_structure()
        print("✓ Error response structure test passed")
        
        print("\n8. Testing correlation ID tracking...")
        test_instance.setup_method()
        test_instance.test_correlation_id_tracking()
        print("✓ Correlation ID tracking test passed")
        
        print("\n🎉 All local workflow tests passed!")
        
    except Exception as e:
        print(f"\n❌ Local test failed: {e}")
        raise


if __name__ == "__main__":
    run_local_tests()