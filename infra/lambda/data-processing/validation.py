"""
Data Validation Module for Georgia Tech Enrollment Data Processing

This module provides validation functions for enrollment data processing parameters,
including course range format validation and subject filtering validation.
"""

import re
import logging
from typing import List, Tuple, Dict, Any, Optional

logger = logging.getLogger(__name__)

class ValidationError(Exception):
    """Custom exception for validation errors with detailed messages."""
    
    def __init__(self, message: str, field: str, value: Any, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.field = field
        self.value = value
        self.details = details or {}

def validate_course_ranges(ranges: List[List[int]]) -> List[str]:
    """
    Validate course range format.
    
    Validates that course ranges are integer pairs separated by hyphens
    and returns detailed error messages for invalid formats.
    
    Args:
        ranges: List of range pairs, each containing [start, end] integers
        
    Returns:
        List of error messages (empty if all ranges are valid)
        
    Raises:
        ValidationError: If ranges parameter is not in expected format
    """
    errors = []
    
    try:
        if not isinstance(ranges, list):
            raise ValidationError(
                "Course ranges must be provided as a list",
                "ranges",
                ranges,
                {"expected_type": "list", "actual_type": type(ranges).__name__}
            )
        
        if len(ranges) == 0:
            # Empty ranges list is valid - means no filtering by course number
            return errors
        
        for i, range_item in enumerate(ranges):
            range_errors = _validate_single_range(range_item, i)
            errors.extend(range_errors)
        
        logger.info(f"Validated {len(ranges)} course ranges with {len(errors)} errors")
        return errors
        
    except ValidationError:
        raise
    except Exception as e:
        logger.error(f"Unexpected error validating course ranges: {e}")
        raise ValidationError(
            f"Unexpected validation error: {str(e)}",
            "ranges",
            ranges,
            {"error_type": type(e).__name__}
        ) from e

def _validate_single_range(range_item: Any, index: int) -> List[str]:
    """
    Validate a single course range pair.
    
    Args:
        range_item: Single range item to validate
        index: Index of the range in the list (for error messages)
        
    Returns:
        List of error messages for this range
    """
    errors = []
    
    try:
        # Check if range is a list/array
        if not isinstance(range_item, (list, tuple)):
            errors.append(
                f"Range {index + 1} must be a list of two integers, got {type(range_item).__name__}: {range_item}"
            )
            return errors
        
        # Check if range has exactly 2 elements
        if len(range_item) != 2:
            errors.append(
                f"Range {index + 1} must contain exactly 2 integers, got {len(range_item)} elements: {range_item}"
            )
            return errors
        
        start, end = range_item
        
        # Check if both elements are integers
        if not isinstance(start, int):
            errors.append(
                f"Range {index + 1} start value must be an integer, got {type(start).__name__}: {start}"
            )
        
        if not isinstance(end, int):
            errors.append(
                f"Range {index + 1} end value must be an integer, got {type(end).__name__}: {end}"
            )
        
        # If both are integers, check logical constraints
        if isinstance(start, int) and isinstance(end, int):
            if start < 0:
                errors.append(
                    f"Range {index + 1} start value must be non-negative, got: {start}"
                )
            
            if end < 0:
                errors.append(
                    f"Range {index + 1} end value must be non-negative, got: {end}"
                )
            
            if start > end:
                errors.append(
                    f"Range {index + 1} start value ({start}) must be less than or equal to end value ({end})"
                )
            
            # Check for reasonable course number bounds (GT courses are typically 1000-9999)
            if start > 9999:
                errors.append(
                    f"Range {index + 1} start value ({start}) exceeds typical course number range (1000-9999)"
                )
            
            if end > 9999:
                errors.append(
                    f"Range {index + 1} end value ({end}) exceeds typical course number range (1000-9999)"
                )
        
        return errors
        
    except Exception as e:
        logger.error(f"Error validating range {index + 1}: {e}")
        return [f"Range {index + 1} validation failed: {str(e)}"]

def validate_subjects(subjects: List[str]) -> List[str]:
    """
    Validate subject codes.
    
    Validates subject code format and normalizes them to uppercase
    for case-insensitive filtering.
    
    Args:
        subjects: List of subject code strings
        
    Returns:
        List of error messages (empty if all subjects are valid)
        
    Raises:
        ValidationError: If subjects parameter is not in expected format
    """
    errors = []
    
    try:
        if not isinstance(subjects, list):
            raise ValidationError(
                "Subject codes must be provided as a list",
                "subjects",
                subjects,
                {"expected_type": "list", "actual_type": type(subjects).__name__}
            )
        
        if len(subjects) == 0:
            # Empty subjects list is valid - means no filtering by subject
            return errors
        
        # Pattern for valid GT subject codes (2-4 letters, typically)
        subject_pattern = re.compile(r'^[A-Za-z]{2,4}$')
        
        for i, subject in enumerate(subjects):
            subject_errors = _validate_single_subject(subject, i, subject_pattern)
            errors.extend(subject_errors)
        
        logger.info(f"Validated {len(subjects)} subject codes with {len(errors)} errors")
        return errors
        
    except ValidationError:
        raise
    except Exception as e:
        logger.error(f"Unexpected error validating subjects: {e}")
        raise ValidationError(
            f"Unexpected validation error: {str(e)}",
            "subjects",
            subjects,
            {"error_type": type(e).__name__}
        ) from e

def _validate_single_subject(subject: Any, index: int, pattern: re.Pattern) -> List[str]:
    """
    Validate a single subject code.
    
    Args:
        subject: Single subject code to validate
        index: Index of the subject in the list (for error messages)
        pattern: Compiled regex pattern for subject validation
        
    Returns:
        List of error messages for this subject
    """
    errors = []
    
    try:
        # Check if subject is a string
        if not isinstance(subject, str):
            errors.append(
                f"Subject {index + 1} must be a string, got {type(subject).__name__}: {subject}"
            )
            return errors
        
        # Check if subject is empty
        if not subject.strip():
            errors.append(
                f"Subject {index + 1} cannot be empty or whitespace-only"
            )
            return errors
        
        # Check if subject matches expected pattern
        if not pattern.match(subject.strip()):
            errors.append(
                f"Subject {index + 1} '{subject}' is not a valid subject code format (expected 2-4 letters)"
            )
        
        return errors
        
    except Exception as e:
        logger.error(f"Error validating subject {index + 1}: {e}")
        return [f"Subject {index + 1} validation failed: {str(e)}"]

def normalize_subjects(subjects: List[str]) -> List[str]:
    """
    Normalize subject codes to uppercase for case-insensitive filtering.
    
    Subject filtering should be case-insensitive.
    This function normalizes all subject codes to uppercase.
    
    Args:
        subjects: List of subject code strings
        
    Returns:
        List of normalized (uppercase) subject codes
        
    Raises:
        ValidationError: If subjects parameter is not valid
    """
    try:
        if not isinstance(subjects, list):
            raise ValidationError(
                "Subject codes must be provided as a list",
                "subjects",
                subjects,
                {"expected_type": "list", "actual_type": type(subjects).__name__}
            )
        
        normalized = []
        for subject in subjects:
            if isinstance(subject, str):
                normalized.append(subject.strip().upper())
            else:
                # This should have been caught by validate_subjects, but handle gracefully
                logger.warning(f"Non-string subject code encountered during normalization: {subject}")
                normalized.append(str(subject).strip().upper())
        
        logger.info(f"Normalized {len(subjects)} subject codes to uppercase")
        return normalized
        
    except ValidationError:
        raise
    except Exception as e:
        logger.error(f"Unexpected error normalizing subjects: {e}")
        raise ValidationError(
            f"Unexpected normalization error: {str(e)}",
            "subjects",
            subjects,
            {"error_type": type(e).__name__}
        ) from e

def validate_term_count(nterms: Any) -> List[str]:
    """
    Validate term count parameter.
    
    Validates that the term count is a positive integer within reasonable bounds
    for fetching the specified number of most recent academic terms.
    
    Args:
        nterms: Term count value to validate
        
    Returns:
        List of error messages (empty if valid)
    """
    errors = []
    
    try:
        # Check if nterms is an integer
        if not isinstance(nterms, int):
            errors.append(f"Term count must be an integer, got {type(nterms).__name__}: {nterms}")
            return errors
        
        # Check if nterms is positive
        if nterms < 1:
            errors.append(f"Term count must be at least 1, got: {nterms}")
        
        # Check reasonable upper bound for performance and practical use
        if nterms > 20:
            errors.append(f"Term count should not exceed 20 terms for performance reasons, got: {nterms}")
        
        # Log validation result
        if not errors:
            logger.debug(f"Term count validation passed: {nterms}")
        
        return errors
        
    except Exception as e:
        logger.error(f"Error validating term count: {e}")
        return [f"Term count validation failed: {str(e)}"]

def validate_summer_inclusion(include_summer: Any) -> List[str]:
    """
    Validate summer term inclusion parameter.
    
    Validates that the summer inclusion flag is a boolean value for controlling
    whether summer terms are included in the term count processing.
    
    Args:
        include_summer: Summer inclusion flag to validate
        
    Returns:
        List of error messages (empty if valid)
    """
    errors = []
    
    try:
        # Check if include_summer is a boolean
        if not isinstance(include_summer, bool):
            errors.append(f"Summer inclusion flag must be a boolean, got {type(include_summer).__name__}: {include_summer}")
        
        # Log validation result
        if not errors:
            logger.debug(f"Summer inclusion validation passed: {include_summer}")
        
        return errors
        
    except Exception as e:
        logger.error(f"Error validating summer inclusion: {e}")
        return [f"Summer inclusion validation failed: {str(e)}"]

def validate_enrollment_parameters(params: Dict[str, Any]) -> Optional[Dict[str, List[str]]]:
    """
    Comprehensive validation of enrollment generation parameters.
    
    This function validates all parameters according to the requirements,
    providing detailed error messages for each validation failure.
    
    Args:
        params: Dictionary of request parameters to validate
        
    Returns:
        Dictionary of validation errors by field name, or None if all valid
    """
    validation_errors = {}
    
    try:
        # Validate nterms parameter
        nterms = params.get('nterms', 1)
        nterms_errors = validate_term_count(nterms)
        if nterms_errors:
            validation_errors['nterms'] = nterms_errors
        
        # Validate include_summer parameter
        include_summer = params.get('include_summer', True)
        summer_errors = validate_summer_inclusion(include_summer)
        if summer_errors:
            validation_errors['include_summer'] = summer_errors
        
        # Validate subjects parameter
        subjects = params.get('subjects', [])
        try:
            subject_errors = validate_subjects(subjects)
            if subject_errors:
                validation_errors['subjects'] = subject_errors
        except ValidationError as e:
            validation_errors['subjects'] = [str(e)]
        
        # Validate ranges parameter
        ranges = params.get('ranges', [])
        try:
            range_errors = validate_course_ranges(ranges)
            if range_errors:
                validation_errors['ranges'] = range_errors
        except ValidationError as e:
            validation_errors['ranges'] = [str(e)]
        
        # Validate boolean parameters
        boolean_params = ['include_summer', 'save_all', 'save_grouped']
        for param in boolean_params:
            value = params.get(param, False)
            if not isinstance(value, bool):
                if param not in validation_errors:
                    validation_errors[param] = []
                validation_errors[param].append(f'{param} must be a boolean value')
        
        # Validate output format options
        save_all = params.get('save_all', True)
        save_grouped = params.get('save_grouped', False)
        
        # Ensure at least one output format is requested
        if not save_all and not save_grouped:
            if 'output_format' not in validation_errors:
                validation_errors['output_format'] = []
            validation_errors['output_format'].append(
                'At least one output format must be requested (save_all or save_grouped must be true)'
            )
        

        
        # Return None if no errors, otherwise return the errors dictionary
        return validation_errors if validation_errors else None
        
    except Exception as e:
        logger.error(f"Unexpected error in parameter validation: {e}")
        return {'validation_system': [f'Parameter validation system error: {str(e)}']}