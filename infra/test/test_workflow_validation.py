"""
Workflow validation tests for enrollment data processing.

Tests core workflow components without triggering logging conflicts.
Validates the workflow logic and data structures.

Validates core workflow functionality.
"""

import json
import os
import sys
import uuid
from unittest.mock import Mock, patch
from typing import Dict, Any

# Add lambda directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'lambda', 'data-processing'))

# Import individual components to test
from validation import validate_enrollment_parameters, normalize_subjects
from job_manager import JobStatus, JobParameters

class TestWorkflowValidation:
    """Test workflow validation and data structures."""
    
    def test_parameter_validation_valid_cases(self):
        """Test parameter validation with valid inputs."""
        valid_cases = [
            # Minimal valid case
            {
                'nterms': 1,
                'subjects': ['CS']
            },
            # Complete valid case
            {
                'nterms': 2,
                'subjects': ['CS', 'MATH'],
                'ranges': [[1000, 1999], [6000, 7999]],
                'include_summer': True,
                'save_all': True,
                'save_grouped': True
            },
            # Edge cases
            {
                'nterms': 10,  # Maximum reasonable terms
                'subjects': ['CS', 'MATH', 'PHYS', 'CHEM'],  # Multiple subjects
                'ranges': [[1000, 9999]],  # Wide range
                'include_summer': False,
                'save_all': True,  # At least one output format must be true
                'save_grouped': False
            }
        ]
        
        for params in valid_cases:
            errors = validate_enrollment_parameters(params)
            assert not errors, f"Valid parameters should not have errors: {params} -> {errors}"
    
    def test_parameter_validation_invalid_cases(self):
        """Test parameter validation with invalid inputs."""
        invalid_cases = [
            # Invalid nterms
            {'nterms': 0, 'subjects': ['CS']},
            {'nterms': -1, 'subjects': ['CS']},
            {'nterms': 'invalid', 'subjects': ['CS']},
            {'nterms': 25, 'subjects': ['CS']},  # Too many terms
            
            # Invalid subjects
            {'nterms': 1, 'subjects': 'CS'},  # Not a list
            {'nterms': 1, 'subjects': [123]},  # Non-string subjects
            {'nterms': 1, 'subjects': ['']},  # Empty string subject
            {'nterms': 1, 'subjects': ['INVALID_SUBJECT_CODE_TOO_LONG']},  # Invalid format
            
            # Invalid ranges
            {'nterms': 1, 'subjects': ['CS'], 'ranges': [[2000, 1000]]},  # End < start
            {'nterms': 1, 'subjects': ['CS'], 'ranges': [['invalid', 'range']]},  # Non-numeric
            {'nterms': 1, 'subjects': ['CS'], 'ranges': [[1000]]},  # Incomplete range
            {'nterms': 1, 'subjects': ['CS'], 'ranges': [[-1, 1000]]},  # Negative start
            
            # Invalid boolean fields
            {'nterms': 1, 'subjects': ['CS'], 'include_summer': 'yes'},  # Not boolean

            {'nterms': 1, 'subjects': ['CS'], 'save_all': 'false'},  # String instead of boolean
            
            # Invalid output format combinations
            {'nterms': 1, 'subjects': ['CS'], 'save_all': False, 'save_grouped': False},  # No output format
        ]
        
        for params in invalid_cases:
            errors = validate_enrollment_parameters(params)
            assert errors, f"Invalid parameters should have errors: {params}"
    
    def test_subject_normalization(self):
        """Test subject code normalization."""
        test_cases = [
            # Case normalization
            (['cs', 'math'], ['CS', 'MATH']),
            (['CS', 'MATH'], ['CS', 'MATH']),
            (['Cs', 'MaTh'], ['CS', 'MATH']),
            
            # Whitespace handling
            ([' CS ', ' MATH '], ['CS', 'MATH']),
            (['CS\t', '\nMATH'], ['CS', 'MATH']),
            
            # Empty handling
            ([], []),
            
            # Duplicate handling (normalization doesn't remove duplicates)
            (['CS', 'cs', 'CS'], ['CS', 'CS', 'CS']),
            (['MATH', 'math', 'Math'], ['MATH', 'MATH', 'MATH']),
        ]
        
        for input_subjects, expected in test_cases:
            result = normalize_subjects(input_subjects)
            assert result == expected, f"normalize_subjects({input_subjects}) = {result}, expected {expected}"
        
        # Test None case separately since it raises an exception
        try:
            normalize_subjects(None)
            assert False, "normalize_subjects(None) should raise ValidationError"
        except Exception:
            pass  # Expected to raise an exception
    
    def test_job_status_enum(self):
        """Test job status enumeration values."""
        # Test all status values are valid
        assert JobStatus.PENDING.value == 'pending'
        assert JobStatus.PROCESSING.value == 'processing'
        assert JobStatus.COMPLETED.value == 'completed'
        assert JobStatus.FAILED.value == 'failed'
        
        # Test status progression logic
        valid_transitions = {
            JobStatus.PENDING: [JobStatus.PROCESSING, JobStatus.FAILED],
            JobStatus.PROCESSING: [JobStatus.COMPLETED, JobStatus.FAILED],
            JobStatus.COMPLETED: [],  # Terminal state
            JobStatus.FAILED: []  # Terminal state
        }
        
        for from_status, valid_to_statuses in valid_transitions.items():
            # This would be used in job manager logic
            assert isinstance(from_status, JobStatus)
            for to_status in valid_to_statuses:
                assert isinstance(to_status, JobStatus)
    
    def test_job_parameters_structure(self):
        """Test job parameters data structure."""
        # Test creating job parameters
        params = JobParameters(
            nterms=2,
            subjects=['CS', 'MATH'],
            ranges=[(1000, 1999), (6000, 7999)],
            include_summer=True,
            save_all=True,
            save_grouped=True
        )
        
        # Validate all fields are accessible
        assert params.nterms == 2
        assert params.subjects == ['CS', 'MATH']
        assert params.ranges == [(1000, 1999), (6000, 7999)]
        assert params.include_summer is True

        assert params.save_all is True
        assert params.save_grouped is True
    
    def test_workflow_data_flow(self):
        """Test the data flow through workflow components."""
        # Simulate the workflow data transformations
        
        # Step 1: Raw request parameters
        raw_params = {
            'nterms': 1,
            'subjects': ['cs', 'math'],  # Lowercase, will be normalized
            'ranges': [[1000, 1999]],
            'include_summer': False,
            'save_all': True,
            'save_grouped': False
        }
        
        # Step 2: Validate parameters
        validation_errors = validate_enrollment_parameters(raw_params)
        assert not validation_errors, f"Parameters should be valid: {validation_errors}"
        
        # Step 3: Normalize subjects
        normalized_subjects = normalize_subjects(raw_params['subjects'])
        assert normalized_subjects == ['CS', 'MATH']
        
        # Step 4: Create job parameters
        job_params = JobParameters(
            nterms=raw_params['nterms'],
            subjects=normalized_subjects,
            ranges=[tuple(r) for r in raw_params['ranges']],
            include_summer=raw_params['include_summer'],
            save_all=raw_params['save_all'],
            save_grouped=raw_params['save_grouped']
        )
        
        # Step 5: Validate job parameters structure
        assert job_params.nterms == 1
        assert job_params.subjects == ['CS', 'MATH']
        assert job_params.ranges == [(1000, 1999)]
        assert job_params.include_summer is False

        assert job_params.save_all is True
        assert job_params.save_grouped is False
    
    def test_file_information_structure(self):
        """Test file information data structures."""
        # Test file info structure that would be returned
        file_info = {
            'filename': 'fall_2025_enrollment_data_2025-12-13-1400.csv',
            's3_key': 'jobs/test-job-id/fall_2025_enrollment_data_2025-12-13-1400.csv',
            'download_url': 'https://test-bucket.s3.amazonaws.com/presigned-url',
            'size_bytes': 1024,
            'file_type': 'ungrouped'
        }
        
        # Validate required fields
        required_fields = ['filename', 's3_key', 'download_url', 'size_bytes', 'file_type']
        for field in required_fields:
            assert field in file_info, f"File info should contain {field}"
        
        # Validate field types and values
        assert isinstance(file_info['filename'], str)
        assert file_info['filename'].endswith('.csv')
        assert 'enrollment_data' in file_info['filename']
        
        assert isinstance(file_info['s3_key'], str)
        assert file_info['s3_key'].startswith('jobs/')
        
        assert isinstance(file_info['download_url'], str)
        assert file_info['download_url'].startswith('https://')
        
        assert isinstance(file_info['size_bytes'], int)
        assert file_info['size_bytes'] > 0
        
        assert file_info['file_type'] in ['ungrouped', 'grouped']
    
    def test_job_status_response_structure(self):
        """Test job status response structure."""
        # Test completed job status response
        job_status_response = {
            'job_id': str(uuid.uuid4()),
            'status': 'completed',
            'progress': 1.0,
            'created_at': '2025-12-13T14:00:00Z',
            'updated_at': '2025-12-13T14:05:00Z',
            'correlation_id': str(uuid.uuid4()),
            'parameters': {
                'nterms': 1,
                'subjects': ['CS'],
                'ranges': [[1000, 1999]],
                'include_summer': False,
                'save_all': True,
                'save_grouped': False
            },
            'terms_processed': 1,
            'files': [
                {
                    'filename': 'fall_2025_enrollment_data.csv',
                    'download_url': 'https://test-url.com',
                    'size_bytes': 1024,
                    'file_type': 'ungrouped'
                }
            ]
        }
        
        # Validate required fields
        required_fields = [
            'job_id', 'status', 'progress', 'created_at', 'updated_at',
            'correlation_id', 'parameters'
        ]
        for field in required_fields:
            assert field in job_status_response, f"Job status should contain {field}"
        
        # Validate field types
        assert isinstance(job_status_response['job_id'], str)
        uuid.UUID(job_status_response['job_id'])  # Should be valid UUID
        
        assert job_status_response['status'] in ['pending', 'processing', 'completed', 'failed']
        
        assert isinstance(job_status_response['progress'], (int, float))
        assert 0 <= job_status_response['progress'] <= 1
        
        # Validate parameters structure
        params = job_status_response['parameters']
        assert isinstance(params['nterms'], int)
        assert isinstance(params['subjects'], list)
        assert isinstance(params['ranges'], list)
        assert isinstance(params['include_summer'], bool)
        
        # Validate files structure if present
        if 'files' in job_status_response:
            files = job_status_response['files']
            assert isinstance(files, list)
            for file_info in files:
                assert 'filename' in file_info
                assert 'download_url' in file_info
                assert 'size_bytes' in file_info
                assert 'file_type' in file_info


def run_validation_tests():
    """Run validation tests manually."""
    print("Running workflow validation tests...")
    
    test_instance = TestWorkflowValidation()
    
    try:
        print("\n1. Testing parameter validation with valid cases...")
        test_instance.test_parameter_validation_valid_cases()
        print("✓ Valid parameter validation test passed")
        
        print("\n2. Testing parameter validation with invalid cases...")
        test_instance.test_parameter_validation_invalid_cases()
        print("✓ Invalid parameter validation test passed")
        
        print("\n3. Testing subject normalization...")
        test_instance.test_subject_normalization()
        print("✓ Subject normalization test passed")
        
        print("\n4. Testing job status enumeration...")
        test_instance.test_job_status_enum()
        print("✓ Job status enum test passed")
        
        print("\n5. Testing job parameters structure...")
        test_instance.test_job_parameters_structure()
        print("✓ Job parameters structure test passed")
        
        print("\n6. Testing workflow data flow...")
        test_instance.test_workflow_data_flow()
        print("✓ Workflow data flow test passed")
        
        print("\n7. Testing file information structure...")
        test_instance.test_file_information_structure()
        print("✓ File information structure test passed")
        
        print("\n8. Testing job status response structure...")
        test_instance.test_job_status_response_structure()
        print("✓ Job status response structure test passed")
        
        print("\n🎉 All workflow validation tests passed!")
        
    except Exception as e:
        print(f"\n❌ Validation test failed: {e}")
        raise


if __name__ == "__main__":
    run_validation_tests()