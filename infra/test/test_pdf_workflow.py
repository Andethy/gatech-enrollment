"""
Tests for PDF processing workflow.

Tests the end-to-end process of:
1. Uploading room capacity PDF files
2. Verifying parsing and CSV generation
3. Testing integration with enrollment data processing

Validates PDF processing functionality.
"""

import json
import os
import sys
import uuid
import pytest
from unittest.mock import Mock, patch, MagicMock
from typing import Dict, Any
import pandas as pd
from io import BytesIO

# Add lambda directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'lambda', 'data-processing'))

# Import the data processing components (PDF processing is now deployment-time)
from index import lambda_handler, handle_capacity_data_request

class TestPDFWorkflow:
    """Test capacity data workflow (simplified architecture without runtime PDF processing)."""
    
    def setup_method(self):
        """Set up test environment for each test."""
        # Mock environment variables
        os.environ['S3_BUCKET_NAME'] = 'test-bucket'
        os.environ['LOG_LEVEL'] = 'INFO'
    
    def test_unsupported_pdf_upload_endpoint(self):
        """Test that PDF upload endpoint is no longer supported (simplified architecture)."""
        # Create a mock event for PDF upload (should now return 404)
        event = {
            'httpMethod': 'POST',
            'path': '/api/v1/capacity/upload',
            'headers': {
                'content-type': 'multipart/form-data; boundary=----WebKitFormBoundary7MA4YWxkTrZu0gW'
            },
            'body': self._create_mock_multipart_body(),
            'isBase64Encoded': False
        }
        
        context = Mock()
        context.aws_request_id = 'test-request-id'
        
        # Call the handler - should return 404 since PDF upload is no longer supported
        response = lambda_handler(event, context)
        
        # Should return 404 for unsupported endpoint
        assert response['statusCode'] == 404
        assert 'body' in response
        
        response_body = json.loads(response['body'])
        assert 'error' in response_body
        assert 'not found' in response_body['error'].lower() or 'endpoint not found' in response_body['error'].lower()
    
    def test_capacity_data_request_structure(self):
        """Test that capacity data requests return proper structure."""
        # Create a mock event for capacity data request
        event = {
            'httpMethod': 'GET',
            'path': '/api/v1/capacity/data',
            'queryStringParameters': None
        }
        
        context = Mock()
        context.aws_request_id = 'test-request-id'
        
        # Mock FileManager
        with patch('index.FileManager') as mock_file_manager_class:
            mock_file_manager = Mock()
            mock_file_manager_class.return_value = mock_file_manager
            
            # Mock file metadata and presigned URL
            mock_file_manager.get_file_metadata.return_value = {
                'size_bytes': 1024,
                'last_modified': '2024-01-01T12:00:00Z'
            }
            mock_file_manager.generate_presigned_url.return_value = 'https://test-download-url.com'
            
            # Call the handler
            response = lambda_handler(event, context)
            
            # Validate response structure
            assert response['statusCode'] == 200
            assert 'body' in response
            
            response_body = json.loads(response['body'])
            
            # Validate required fields for simplified capacity data endpoint
            assert 'download_url' in response_body
            assert 'filename' in response_body
            assert 'last_modified' in response_body
            assert 'size_bytes' in response_body
            
            # Verify FileManager methods were called
            mock_file_manager.get_file_metadata.assert_called_once_with('capacity-data/room_capacity_data.csv')
            mock_file_manager.generate_presigned_url.assert_called_once()
    
    def test_capacity_data_deployment_time_processing(self):
        """Test that capacity data is processed at deployment time (not runtime)."""
        # This test validates that the system expects pre-processed capacity data
        # rather than processing PDFs at runtime
        
        # Test that the capacity data endpoint expects pre-existing data
        event = {
            'httpMethod': 'GET',
            'path': '/api/v1/capacity/data'
        }
        
        context = Mock()
        context.aws_request_id = 'test-request-id'
        
        # Mock FileManager to simulate pre-processed data exists
        with patch('index.FileManager') as mock_file_manager_class:
            mock_file_manager = Mock()
            mock_file_manager_class.return_value = mock_file_manager
            
            # Mock that capacity data exists (processed at deployment time)
            mock_file_manager.get_file_metadata.return_value = {
                'size_bytes': 2048,
                'last_modified': '2024-01-01T12:00:00Z'
            }
            mock_file_manager.generate_presigned_url.return_value = 'https://capacity-data-url.com'
            
            response = lambda_handler(event, context)
            
            # Should successfully return pre-processed data
            assert response['statusCode'] == 200
            response_body = json.loads(response['body'])
            assert response_body['filename'] == 'room_capacity_data.csv'
            assert 'download_url' in response_body
    
    def test_capacity_data_not_found_handling(self):
        """Test handling when capacity data doesn't exist."""
        event = {
            'httpMethod': 'GET',
            'path': '/api/v1/capacity/data'
        }
        
        context = Mock()
        context.aws_request_id = 'test-request-id'
        
        # Mock FileManager to simulate missing capacity data
        with patch('index.FileManager') as mock_file_manager_class:
            mock_file_manager = Mock()
            mock_file_manager_class.return_value = mock_file_manager
            
            # Mock file not found error
            mock_file_manager.get_file_metadata.side_effect = Exception("NoSuchKey")
            
            response = lambda_handler(event, context)
            
            # Should return 404 error
            assert response['statusCode'] == 404
            response_body = json.loads(response['body'])
            assert 'error' in response_body
    
    def test_capacity_data_file_manager_error_handling(self):
        """Test handling of FileManager errors when accessing capacity data."""
        event = {
            'httpMethod': 'GET',
            'path': '/api/v1/capacity/data'
        }
        
        context = Mock()
        context.aws_request_id = 'test-request-id'
        
        # Mock FileManager to simulate various error conditions
        with patch('index.FileManager') as mock_file_manager_class:
            mock_file_manager = Mock()
            mock_file_manager_class.return_value = mock_file_manager
            
            # Mock file metadata success but presigned URL failure
            mock_file_manager.get_file_metadata.return_value = {
                'size_bytes': 1024,
                'last_modified': '2024-01-01T12:00:00Z'
            }
            mock_file_manager.generate_presigned_url.side_effect = Exception("Failed to generate URL")
            
            response = lambda_handler(event, context)
            
            # Should return 500 error for internal processing failure
            assert response['statusCode'] == 500
            response_body = json.loads(response['body'])
            assert 'error' in response_body
    
    def test_capacity_data_access_permissions(self):
        """Test handling of S3 access permission errors."""
        event = {
            'httpMethod': 'GET',
            'path': '/api/v1/capacity/data'
        }
        
        context = Mock()
        context.aws_request_id = 'test-request-id'
        
        with patch('index.FileManager') as mock_file_manager_class:
            mock_file_manager = Mock()
            mock_file_manager_class.return_value = mock_file_manager
            
            # Mock access denied error
            mock_file_manager.get_file_metadata.side_effect = Exception("AccessDenied")
            
            response = lambda_handler(event, context)
            
            # Should return 500 error for access issues
            assert response['statusCode'] == 500
            response_body = json.loads(response['body'])
            assert 'error' in response_body
    
    def test_capacity_data_response_format(self):
        """Test that capacity data response has correct format."""
        event = {
            'httpMethod': 'GET',
            'path': '/api/v1/capacity/data'
        }
        
        context = Mock()
        context.aws_request_id = 'test-request-id'
        
        with patch('index.FileManager') as mock_file_manager_class:
            mock_file_manager = Mock()
            mock_file_manager_class.return_value = mock_file_manager
            
            # Mock successful file access
            mock_file_manager.get_file_metadata.return_value = {
                'size_bytes': 2048,
                'last_modified': '2024-01-01T12:00:00Z'
            }
            mock_file_manager.generate_presigned_url.return_value = 'https://test-url.com/capacity.csv'
            
            response = lambda_handler(event, context)
            
            # Validate response format
            assert response['statusCode'] == 200
            assert 'headers' in response
            assert 'body' in response
            
            # Check headers
            headers = response['headers']
            assert headers['Content-Type'] == 'application/json'
            assert headers['Access-Control-Allow-Origin'] == '*'
            
            # Check response body structure
            response_body = json.loads(response['body'])
            required_fields = ['download_url', 'filename', 'last_modified', 'size_bytes']
            for field in required_fields:
                assert field in response_body, f"Missing required field: {field}"
            
            assert response_body['filename'] == 'room_capacity_data.csv'
            assert response_body['size_bytes'] == 2048
    
    def test_capacity_data_cors_headers(self):
        """Test that capacity data endpoint returns proper CORS headers."""
        event = {
            'httpMethod': 'GET',
            'path': '/api/v1/capacity/data'
        }
        
        context = Mock()
        context.aws_request_id = 'test-request-id'
        
        with patch('index.FileManager') as mock_file_manager_class:
            mock_file_manager = Mock()
            mock_file_manager_class.return_value = mock_file_manager
            
            # Mock successful response
            mock_file_manager.get_file_metadata.return_value = {
                'size_bytes': 1024,
                'last_modified': '2024-01-01T12:00:00Z'
            }
            mock_file_manager.generate_presigned_url.return_value = 'https://test-url.com'
            
            response = lambda_handler(event, context)
            
            # Check CORS headers are present
            headers = response['headers']
            assert 'Access-Control-Allow-Origin' in headers
            assert 'Access-Control-Allow-Headers' in headers
            assert 'Access-Control-Allow-Methods' in headers
            
            assert headers['Access-Control-Allow-Origin'] == '*'
            assert 'Content-Type' in headers['Access-Control-Allow-Headers']
            assert 'Authorization' in headers['Access-Control-Allow-Headers']
            assert 'GET' in headers['Access-Control-Allow-Methods']
    
    def test_unsupported_endpoint(self):
        """Test handling of unsupported endpoints."""
        event = {
            'httpMethod': 'DELETE',
            'path': '/api/v1/capacity/delete'
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
        from index import create_error_response
        
        correlation_id = str(uuid.uuid4())
        details = {'test_field': 'test_value'}
        
        response = create_error_response(400, 'Test error message', details, correlation_id)
        
        # Validate error response structure
        assert 'statusCode' in response
        assert 'headers' in response
        assert 'body' in response
        
        # Validate headers
        headers = response['headers']
        assert 'Content-Type' in headers
        assert 'Access-Control-Allow-Origin' in headers
        assert 'X-Correlation-ID' in headers
        assert headers['X-Correlation-ID'] == correlation_id
        
        # Validate error body structure
        response_body = json.loads(response['body'])
        assert 'error' in response_body
        assert 'status_code' in response_body
        assert 'timestamp' in response_body
        assert 'error_code' in response_body
        assert 'correlation_id' in response_body
        assert 'details' in response_body
        
        assert response_body['error'] == 'Test error message'
        assert response_body['status_code'] == 400
        assert response_body['correlation_id'] == correlation_id
        assert response_body['details'] == details
    
    def test_capacity_data_correlation_id_tracking(self):
        """Test that capacity data requests include correlation ID tracking."""
        event = {
            'httpMethod': 'GET',
            'path': '/api/v1/capacity/data'
        }
        
        context = Mock()
        context.aws_request_id = 'test-request-id'
        
        with patch('index.FileManager') as mock_file_manager_class:
            mock_file_manager = Mock()
            mock_file_manager_class.return_value = mock_file_manager
            
            # Mock successful response
            mock_file_manager.get_file_metadata.return_value = {
                'size_bytes': 1024,
                'last_modified': '2024-01-01T12:00:00Z'
            }
            mock_file_manager.generate_presigned_url.return_value = 'https://test-url.com'
            
            response = lambda_handler(event, context)
            
            # Check that correlation ID is included in headers
            assert 'X-Correlation-ID' in response['headers']
            
            # Check that correlation ID is a valid UUID format
            correlation_id = response['headers']['X-Correlation-ID']
            try:
                uuid.UUID(correlation_id)
                correlation_id_valid = True
            except ValueError:
                correlation_id_valid = False
            
            assert correlation_id_valid, "Correlation ID should be a valid UUID"
    
    def _create_mock_multipart_body(self):
        """Create a mock multipart form body for testing."""
        boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
        body = f"""------WebKitFormBoundary7MA4YWxkTrZu0gW\r
Content-Disposition: form-data; name="file"; filename="test.pdf"\r
Content-Type: application/pdf\r
\r
%PDF-1.4 mock pdf content\r
------WebKitFormBoundary7MA4YWxkTrZu0gW--\r
"""
        return body


def run_pdf_tests():
    """Run capacity data workflow tests manually."""
    print("Running capacity data workflow tests...")
    
    test_instance = TestPDFWorkflow()
    
    try:
        print("\n1. Testing unsupported PDF upload endpoint...")
        test_instance.setup_method()
        test_instance.test_unsupported_pdf_upload_endpoint()
        print("✓ Unsupported PDF upload test passed")
        
        print("\n2. Testing capacity data request structure...")
        test_instance.setup_method()
        test_instance.test_capacity_data_request_structure()
        print("✓ Capacity data structure test passed")
        
        print("\n3. Testing deployment-time processing...")
        test_instance.setup_method()
        test_instance.test_capacity_data_deployment_time_processing()
        print("✓ Deployment-time processing test passed")
        
        print("\n4. Testing capacity data not found handling...")
        test_instance.setup_method()
        test_instance.test_capacity_data_not_found_handling()
        print("✓ Capacity data not found test passed")
        
        print("\n5. Testing file manager error handling...")
        test_instance.setup_method()
        test_instance.test_capacity_data_file_manager_error_handling()
        print("✓ File manager error handling test passed")
        
        print("\n6. Testing access permissions...")
        test_instance.setup_method()
        test_instance.test_capacity_data_access_permissions()
        print("✓ Access permissions test passed")
        
        print("\n7. Testing response format...")
        test_instance.setup_method()
        test_instance.test_capacity_data_response_format()
        print("✓ Response format test passed")
        
        print("\n8. Testing CORS headers...")
        test_instance.setup_method()
        test_instance.test_capacity_data_cors_headers()
        print("✓ CORS headers test passed")
        
        print("\n9. Testing unsupported endpoint...")
        test_instance.setup_method()
        test_instance.test_unsupported_endpoint()
        print("✓ Unsupported endpoint test passed")
        
        print("\n10. Testing error response structure...")
        test_instance.setup_method()
        test_instance.test_error_response_structure()
        print("✓ Error response structure test passed")
        
        print("\n11. Testing correlation ID tracking...")
        test_instance.setup_method()
        test_instance.test_capacity_data_correlation_id_tracking()
        print("✓ Correlation ID tracking test passed")
        
        print("\n🎉 All capacity data workflow tests passed!")
        
    except Exception as e:
        print(f"\n❌ Capacity data test failed: {e}")
        raise


if __name__ == "__main__":
    run_pdf_tests()