"""
Integration tests for the complete enrollment data workflow.

Tests the end-to-end process of:
1. Submitting enrollment generation requests
2. Verifying job status tracking works correctly
3. Downloading and validating generated CSV files

Validates enrollment data processing integration.
"""

import json
import os
import sys
import time
import uuid
import pytest
import boto3
import requests
from typing import Dict, Any, List
from datetime import datetime, timedelta

# Add lambda directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'lambda', 'data-processing'))

from job_manager import JobManager, JobStatus
from file_manager import FileManager

class TestEnrollmentWorkflow:
    """Integration tests for enrollment data workflow."""
    
    @classmethod
    def setup_class(cls):
        """Set up test environment."""
        # Use test bucket or create one for testing
        cls.bucket_name = os.getenv('TEST_S3_BUCKET_NAME', 'test-gatech-enrollment-bucket')
        cls.api_base_url = os.getenv('TEST_API_BASE_URL', 'https://api.enrollment.cs1332.cc/api/v1')
        cls.auth_token = os.getenv('TEST_AUTH_TOKEN')
        
        # Initialize AWS clients
        cls.s3_client = boto3.client('s3')
        
        # Initialize managers
        cls.job_manager = JobManager(cls.bucket_name)
        cls.file_manager = FileManager(cls.bucket_name)
        
        # Ensure test bucket exists
        try:
            cls.s3_client.head_bucket(Bucket=cls.bucket_name)
        except:
            # Create bucket if it doesn't exist (for local testing)
            try:
                cls.s3_client.create_bucket(Bucket=cls.bucket_name)
            except Exception as e:
                print(f"Warning: Could not create test bucket: {e}")
    
    def test_complete_enrollment_workflow_minimal(self):
        """Test complete workflow with minimal parameters."""
        # Test parameters for a quick request
        request_params = {
            "nterms": 1,
            "subjects": ["CS"],
            "ranges": [[1000, 1999]],
            "include_summer": False,
            "save_all": True,
            "save_grouped": False
        }
        
        # Step 1: Submit enrollment generation request
        job_id = self._submit_enrollment_request(request_params)
        assert job_id is not None, "Job ID should be returned"
        assert isinstance(job_id, str), "Job ID should be a string"
        
        # Validate job ID format (should be UUID)
        try:
            uuid.UUID(job_id)
        except ValueError:
            pytest.fail(f"Job ID {job_id} is not a valid UUID")
        
        # Step 2: Monitor job status until completion
        final_status = self._monitor_job_until_completion(job_id, timeout_seconds=300)
        
        # Step 3: Verify job completed successfully
        assert final_status['status'] == 'completed', f"Job should complete successfully, got: {final_status['status']}"
        assert 'files' in final_status, "Completed job should have files"
        assert len(final_status['files']) > 0, "Should have at least one generated file"
        
        # Step 4: Validate generated files
        self._validate_generated_files(final_status['files'])
        
        # Step 5: Test file download
        self._test_file_downloads(final_status['files'])
    
    def test_complete_enrollment_workflow_comprehensive(self):
        """Test complete workflow with comprehensive parameters."""
        # Test parameters for a more comprehensive request
        request_params = {
            "nterms": 2,
            "subjects": ["CS", "MATH"],
            "ranges": [[1000, 2999], [6000, 7999]],
            "include_summer": True,
            "save_all": True,
            "save_grouped": True
        }
        
        # Step 1: Submit enrollment generation request
        job_id = self._submit_enrollment_request(request_params)
        assert job_id is not None, "Job ID should be returned"
        
        # Step 2: Monitor job status until completion
        final_status = self._monitor_job_until_completion(job_id, timeout_seconds=600)
        
        # Step 3: Verify job completed successfully
        assert final_status['status'] == 'completed', f"Job should complete successfully, got: {final_status['status']}"
        assert 'files' in final_status, "Completed job should have files"
        
        # Should have files due to save_all=True and save_grouped=True
        assert len(final_status['files']) >= 1, "Should have files for comprehensive request"
        
        # Step 4: Validate file types
        file_types = [f.get('file_type', 'unknown') for f in final_status['files']]
        assert 'ungrouped' in file_types, "Should have ungrouped file"
        assert 'grouped' in file_types, "Should have grouped file when save_grouped=True"
        
        # Step 5: Validate generated files
        self._validate_generated_files(final_status['files'])
    
    def test_job_status_tracking_progression(self):
        """Test that job status progresses correctly through states."""
        request_params = {
            "nterms": 1,
            "subjects": ["CS"],
            "ranges": [[1000, 1999]],
            "include_summer": False,
            "save_all": True,
            "save_grouped": False
        }
        
        # Submit request
        job_id = self._submit_enrollment_request(request_params)
        
        # Track status progression
        statuses_seen = []
        start_time = time.time()
        
        while time.time() - start_time < 300:  # 5 minute timeout
            status_response = self._get_job_status(job_id)
            current_status = status_response['status']
            
            if current_status not in statuses_seen:
                statuses_seen.append(current_status)
            
            # Check progress is valid
            progress = status_response.get('progress', 0)
            assert 0 <= progress <= 1, f"Progress should be between 0 and 1, got: {progress}"
            
            if current_status == 'completed':
                break
            elif current_status == 'failed':
                pytest.fail(f"Job failed: {status_response.get('error_message', 'Unknown error')}")
            
            time.sleep(2)  # Check every 2 seconds
        
        # Verify we saw expected status progression
        assert 'pending' in statuses_seen or 'processing' in statuses_seen, "Should see initial status"
        assert 'completed' in statuses_seen, "Should reach completed status"
        
        # Verify final status has required fields
        final_status = self._get_job_status(job_id)
        assert 'created_at' in final_status, "Should have creation timestamp"
        assert 'updated_at' in final_status, "Should have update timestamp"
        assert 'parameters' in final_status, "Should have original parameters"
    
    def test_invalid_job_id_handling(self):
        """Test handling of invalid job IDs."""
        # Test with non-existent UUID
        fake_job_id = str(uuid.uuid4())
        status_response = self._get_job_status(fake_job_id, expect_success=False)
        assert status_response is None or status_response.get('error'), "Should handle non-existent job ID"
        
        # Test with invalid UUID format
        invalid_job_id = "not-a-uuid"
        status_response = self._get_job_status(invalid_job_id, expect_success=False)
        assert status_response is None or status_response.get('error'), "Should handle invalid job ID format"
    
    def test_parameter_validation(self):
        """Test parameter validation in enrollment requests."""
        # Test with invalid parameters
        invalid_params = [
            # Missing required fields
            {},
            # Invalid nterms
            {"nterms": 0, "subjects": ["CS"]},
            {"nterms": -1, "subjects": ["CS"]},
            # Invalid ranges
            {"nterms": 1, "subjects": ["CS"], "ranges": [[2000, 1000]]},  # End < start
            {"nterms": 1, "subjects": ["CS"], "ranges": [["invalid", "range"]]},  # Non-numeric
            # Invalid subjects
            {"nterms": 1, "subjects": []},  # Empty subjects
        ]
        
        for params in invalid_params:
            response = self._submit_enrollment_request(params, expect_success=False)
            assert response is None or 'error' in str(response), f"Should reject invalid params: {params}"
    
    def _submit_enrollment_request(self, params: Dict[str, Any], expect_success: bool = True) -> str:
        """Submit an enrollment generation request."""
        try:
            if self.auth_token:
                headers = {
                    'Authorization': f'Bearer {self.auth_token}',
                    'Content-Type': 'application/json'
                }
            else:
                headers = {'Content-Type': 'application/json'}
            
            response = requests.post(
                f"{self.api_base_url}/enrollment/generate",
                json=params,
                headers=headers,
                timeout=30
            )
            
            if expect_success:
                assert response.status_code in [200, 202], f"Request should succeed, got: {response.status_code} - {response.text}"
                response_data = response.json()
                return response_data.get('job_id')
            else:
                return response.json() if response.status_code != 200 else None
                
        except Exception as e:
            if expect_success:
                pytest.fail(f"Failed to submit enrollment request: {e}")
            return None
    
    def _get_job_status(self, job_id: str, expect_success: bool = True) -> Dict[str, Any]:
        """Get job status."""
        try:
            if self.auth_token:
                headers = {'Authorization': f'Bearer {self.auth_token}'}
            else:
                headers = {}
            
            response = requests.get(
                f"{self.api_base_url}/jobs/{job_id}/status",
                headers=headers,
                timeout=30
            )
            
            if expect_success:
                assert response.status_code == 200, f"Status request should succeed, got: {response.status_code} - {response.text}"
                return response.json()
            else:
                return response.json() if response.status_code != 200 else None
                
        except Exception as e:
            if expect_success:
                pytest.fail(f"Failed to get job status: {e}")
            return None
    
    def _monitor_job_until_completion(self, job_id: str, timeout_seconds: int = 300) -> Dict[str, Any]:
        """Monitor job until completion or timeout."""
        start_time = time.time()
        
        while time.time() - start_time < timeout_seconds:
            status_response = self._get_job_status(job_id)
            current_status = status_response['status']
            
            if current_status == 'completed':
                return status_response
            elif current_status == 'failed':
                error_msg = status_response.get('error_message', 'Unknown error')
                pytest.fail(f"Job {job_id} failed: {error_msg}")
            
            # Log progress
            progress = status_response.get('progress', 0)
            print(f"Job {job_id} status: {current_status}, progress: {progress:.1%}")
            
            time.sleep(5)  # Check every 5 seconds
        
        pytest.fail(f"Job {job_id} did not complete within {timeout_seconds} seconds")
    
    def _validate_generated_files(self, files: List[Dict[str, Any]]):
        """Validate the structure and content of generated files."""
        for file_info in files:
            # Validate file info structure
            assert 'filename' in file_info, "File should have filename"
            assert 'download_url' in file_info, "File should have download URL"
            assert 'size_bytes' in file_info, "File should have size information"
            assert 'file_type' in file_info, "File should have type information"
            
            # Validate filename format
            filename = file_info['filename']
            assert filename.endswith('.csv'), f"File should be CSV: {filename}"
            assert 'enrollment_data' in filename.lower(), f"Filename should indicate enrollment data: {filename}"
            
            # Validate size
            size_bytes = file_info['size_bytes']
            assert size_bytes > 0, f"File should have content: {filename} has {size_bytes} bytes"
            
            # Validate file type
            file_type = file_info['file_type']
            assert file_type in ['ungrouped', 'grouped'], f"File type should be valid: {file_type}"
    
    def _test_file_downloads(self, files: List[Dict[str, Any]]):
        """Test downloading files and validate basic CSV structure."""
        for file_info in files:
            download_url = file_info['download_url']
            filename = file_info['filename']
            
            if not download_url:
                pytest.fail(f"No download URL for file: {filename}")
            
            try:
                # Download file
                response = requests.get(download_url, timeout=60)
                assert response.status_code == 200, f"Download should succeed for {filename}"
                
                # Validate CSV content
                content = response.text
                lines = content.strip().split('\n')
                
                # Should have header and at least some data
                assert len(lines) >= 2, f"CSV should have header and data: {filename}"
                
                # Validate header contains expected columns
                header = lines[0].lower()
                expected_columns = ['term', 'subject', 'course', 'crn', 'enrollment']
                for col in expected_columns:
                    assert col in header, f"CSV should contain {col} column: {filename}"
                
                # Validate data rows are properly formatted
                if len(lines) > 1:
                    data_row = lines[1]
                    # Should have same number of columns as header
                    header_cols = len(lines[0].split(','))
                    data_cols = len(data_row.split(','))
                    assert data_cols == header_cols, f"Data row should match header columns: {filename}"
                
                print(f"Successfully validated file: {filename} ({len(lines)} lines)")
                
            except Exception as e:
                pytest.fail(f"Failed to download or validate file {filename}: {e}")


def run_integration_tests():
    """Run integration tests manually."""
    print("Running enrollment workflow integration tests...")
    
    # Check environment
    bucket_name = os.getenv('TEST_S3_BUCKET_NAME')
    api_url = os.getenv('TEST_API_BASE_URL')
    
    if not bucket_name:
        print("Warning: TEST_S3_BUCKET_NAME not set, using default")
    if not api_url:
        print("Warning: TEST_API_BASE_URL not set, using default")
    
    # Run tests
    test_instance = TestEnrollmentWorkflow()
    test_instance.setup_class()
    
    try:
        print("\n1. Testing minimal enrollment workflow...")
        test_instance.test_complete_enrollment_workflow_minimal()
        print("✓ Minimal workflow test passed")
        
        print("\n2. Testing job status tracking...")
        test_instance.test_job_status_tracking_progression()
        print("✓ Job status tracking test passed")
        
        print("\n3. Testing parameter validation...")
        test_instance.test_parameter_validation()
        print("✓ Parameter validation test passed")
        
        print("\n4. Testing invalid job ID handling...")
        test_instance.test_invalid_job_id_handling()
        print("✓ Invalid job ID handling test passed")
        
        print("\n5. Testing comprehensive enrollment workflow...")
        test_instance.test_complete_enrollment_workflow_comprehensive()
        print("✓ Comprehensive workflow test passed")
        
        print("\n🎉 All integration tests passed!")
        
    except Exception as e:
        print(f"\n❌ Integration test failed: {e}")
        raise


if __name__ == "__main__":
    run_integration_tests()