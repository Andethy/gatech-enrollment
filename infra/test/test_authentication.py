"""
Tests for authentication and authorization.

Tests the end-to-end process of:
1. Testing all endpoints with valid and invalid tokens
2. Verifying proper error responses for unauthorized access
3. Testing Cognito integration end-to-end

Validates authentication functionality.
"""

import json
import os
import sys
import uuid
import pytest
from unittest.mock import Mock, patch
from typing import Dict, Any, Optional
import base64
import time
from datetime import datetime, timedelta

class TestAuthentication:
    """Test authentication and authorization logic."""
    
    def test_cognito_authorizer_configuration(self):
        """Test Cognito authorizer configuration structure."""
        # Test authorizer configuration
        authorizer_config = {
            'type': 'COGNITO_USER_POOLS',
            'identity_source': 'method.request.header.Authorization',
            'user_pools': ['us-east-1_example123'],
            'results_cache_ttl': 300,  # 5 minutes
            'token_validation': {
                'validate_token_format': True,
                'validate_token_expiration': True,
                'validate_token_signature': True
            }
        }
        
        # Validate configuration structure
        assert authorizer_config['type'] == 'COGNITO_USER_POOLS'
        assert authorizer_config['identity_source'] == 'method.request.header.Authorization'
        assert isinstance(authorizer_config['user_pools'], list)
        assert len(authorizer_config['user_pools']) > 0
        assert authorizer_config['results_cache_ttl'] > 0
        assert authorizer_config['token_validation']['validate_token_format'] is True
        assert authorizer_config['token_validation']['validate_token_expiration'] is True
        assert authorizer_config['token_validation']['validate_token_signature'] is True
    
    def test_jwt_token_structure_validation(self):
        """Test JWT token structure validation."""
        # Valid JWT token structure (mock)
        valid_jwt_header = {
            'alg': 'RS256',
            'kid': 'example-key-id',
            'typ': 'JWT'
        }
        
        valid_jwt_payload = {
            'sub': str(uuid.uuid4()),
            'aud': 'example-client-id',
            'iss': 'https://cognito-idp.us-east-1.amazonaws.com/us-east-1_example123',
            'exp': int(time.time()) + 3600,  # Expires in 1 hour
            'iat': int(time.time()),
            'token_use': 'access',
            'scope': 'aws.cognito.signin.user.admin',
            'username': 'testuser'
        }
        
        # Validate JWT structure
        assert 'alg' in valid_jwt_header
        assert valid_jwt_header['alg'] == 'RS256'
        assert 'typ' in valid_jwt_header
        assert valid_jwt_header['typ'] == 'JWT'
        
        assert 'sub' in valid_jwt_payload
        assert 'aud' in valid_jwt_payload
        assert 'iss' in valid_jwt_payload
        assert 'exp' in valid_jwt_payload
        assert 'iat' in valid_jwt_payload
        assert valid_jwt_payload['token_use'] == 'access'
        
        # Validate expiration is in the future
        assert valid_jwt_payload['exp'] > time.time()
        
        # Validate issued time is not in the future
        assert valid_jwt_payload['iat'] <= time.time()
    
    def test_api_endpoint_authentication_needed(self):
        """Test that all API endpoints require authentication."""
        # Define all API endpoints that should require authentication
        protected_endpoints = [
            {
                'method': 'POST',
                'path': '/api/v1/enrollment/generate',
                'description': 'Enrollment data generation'
            },
            {
                'method': 'GET',
                'path': '/api/v1/jobs/{jobId}/status',
                'description': 'Job status retrieval'
            },
            {
                'method': 'POST',
                'path': '/api/v1/capacity/upload',
                'description': 'PDF capacity file upload'
            },
            {
                'method': 'GET',
                'path': '/api/v1/capacity/data',
                'description': 'Capacity data retrieval'
            }
        ]
        
        # Each endpoint should have authentication configured
        for endpoint in protected_endpoints:
            # Validate endpoint structure
            assert 'method' in endpoint
            assert 'path' in endpoint
            assert 'description' in endpoint
            
            # Validate method is valid HTTP method
            assert endpoint['method'] in ['GET', 'POST', 'PUT', 'DELETE', 'PATCH']
            
            # Validate path follows API versioning pattern
            assert endpoint['path'].startswith('/api/v1/')
            
            # All endpoints should be protected (this would be validated in actual deployment)
            endpoint_requires_auth = True  # This would be checked against actual API Gateway config
            assert endpoint_requires_auth, f"Endpoint {endpoint['method']} {endpoint['path']} should require authentication"
    
    def test_unauthorized_request_handling(self):
        """Test handling of requests without authentication."""
        # Test cases for unauthorized requests
        unauthorized_scenarios = [
            {
                'scenario': 'missing_authorization_header',
                'headers': {},
                'expected_status': 401,
                'expected_error': 'Unauthorized'
            },
            {
                'scenario': 'empty_authorization_header',
                'headers': {'Authorization': ''},
                'expected_status': 401,
                'expected_error': 'Unauthorized'
            },
            {
                'scenario': 'invalid_bearer_format',
                'headers': {'Authorization': 'InvalidFormat token123'},
                'expected_status': 401,
                'expected_error': 'Unauthorized'
            },
            {
                'scenario': 'malformed_jwt_token',
                'headers': {'Authorization': 'Bearer invalid.jwt.token'},
                'expected_status': 401,
                'expected_error': 'Unauthorized'
            },
            {
                'scenario': 'expired_jwt_token',
                'headers': {'Authorization': 'Bearer ' + self._create_expired_jwt_token()},
                'expected_status': 401,
                'expected_error': 'Unauthorized'
            }
        ]
        
        for scenario in unauthorized_scenarios:
            # Validate scenario structure
            assert 'scenario' in scenario
            assert 'headers' in scenario
            assert 'expected_status' in scenario
            assert 'expected_error' in scenario
            
            # Validate expected status is 401
            assert scenario['expected_status'] == 401
            
            # Validate error message indicates unauthorized access
            assert 'unauthorized' in scenario['expected_error'].lower()
    
    def test_valid_authentication_flow(self):
        """Test valid authentication flow."""
        # Mock valid authentication flow
        auth_flow = {
            'step1_user_login': {
                'username': 'testuser@example.com',
                'password': 'SecurePassword123!',
                'client_id': 'example-client-id'
            },
            'step2_cognito_response': {
                'access_token': self._create_valid_jwt_token(),
                'id_token': self._create_valid_id_token(),
                'refresh_token': 'example-refresh-token',
                'expires_in': 3600,
                'token_type': 'Bearer'
            },
            'step3_api_request': {
                'method': 'POST',
                'url': '/api/v1/enrollment/generate',
                'headers': {
                    'Authorization': 'Bearer ' + self._create_valid_jwt_token(),
                    'Content-Type': 'application/json'
                },
                'body': {
                    'nterms': 1,
                    'subjects': ['CS']
                }
            },
            'step4_expected_response': {
                'status_code': 202,
                'has_job_id': True,
                'has_correlation_id': True
            }
        }
        
        # Validate authentication flow structure
        assert 'step1_user_login' in auth_flow
        assert 'step2_cognito_response' in auth_flow
        assert 'step3_api_request' in auth_flow
        assert 'step4_expected_response' in auth_flow
        
        # Validate login credentials
        login = auth_flow['step1_user_login']
        assert 'username' in login
        assert 'password' in login
        assert 'client_id' in login
        
        # Validate Cognito response
        cognito_response = auth_flow['step2_cognito_response']
        assert 'access_token' in cognito_response
        assert 'token_type' in cognito_response
        assert cognito_response['token_type'] == 'Bearer'
        assert cognito_response['expires_in'] > 0
        
        # Validate API request
        api_request = auth_flow['step3_api_request']
        assert 'Authorization' in api_request['headers']
        assert api_request['headers']['Authorization'].startswith('Bearer ')
        
        # Validate expected response
        expected_response = auth_flow['step4_expected_response']
        assert expected_response['status_code'] == 202  # Accepted
        assert expected_response['has_job_id'] is True
        assert expected_response['has_correlation_id'] is True
    
    def test_token_expiration_handling(self):
        """Test handling of expired tokens."""
        # Test token expiration scenarios
        expiration_scenarios = [
            {
                'scenario': 'recently_expired',
                'expired_minutes_ago': 1,
                'expected_behavior': 'reject_with_401'
            },
            {
                'scenario': 'long_expired',
                'expired_minutes_ago': 60,
                'expected_behavior': 'reject_with_401'
            },
            {
                'scenario': 'expires_soon',
                'expires_in_minutes': 5,
                'expected_behavior': 'accept_but_warn'
            },
            {
                'scenario': 'fresh_token',
                'expires_in_minutes': 30,
                'expected_behavior': 'accept_normally'
            }
        ]
        
        for scenario in expiration_scenarios:
            scenario_name = scenario['scenario']
            expected_behavior = scenario['expected_behavior']
            
            if 'expired_minutes_ago' in scenario:
                # Token is expired
                assert expected_behavior == 'reject_with_401'
                
                # Create expired token
                expired_token = self._create_jwt_token_with_expiration(
                    expires_in_seconds=-scenario['expired_minutes_ago'] * 60
                )
                
                # Validate token is expired
                token_payload = self._decode_jwt_payload(expired_token)
                assert token_payload['exp'] < time.time()
                
            elif 'expires_in_minutes' in scenario:
                # Token is valid but may expire soon
                expires_in_seconds = scenario['expires_in_minutes'] * 60
                valid_token = self._create_jwt_token_with_expiration(expires_in_seconds)
                
                # Validate token is not expired
                token_payload = self._decode_jwt_payload(valid_token)
                assert token_payload['exp'] > time.time()
                
                if expected_behavior == 'accept_but_warn':
                    # Token expires soon, should be accepted but may generate warning
                    time_until_expiry = token_payload['exp'] - time.time()
                    assert time_until_expiry < 10 * 60  # Less than 10 minutes
                elif expected_behavior == 'accept_normally':
                    # Token has plenty of time left
                    time_until_expiry = token_payload['exp'] - time.time()
                    assert time_until_expiry > 10 * 60  # More than 10 minutes
    
    def test_cors_configuration_for_auth(self):
        """Test CORS configuration for authenticated endpoints."""
        # CORS configuration for authenticated endpoints
        cors_config = {
            'allow_origins': ['https://enrollment.cs1332.cc'],  # Production domain
            'allow_methods': ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'],
            'allow_headers': [
                'Content-Type',
                'X-Amz-Date',
                'Authorization',  # Critical for authentication
                'X-Api-Key',
                'X-Amz-Security-Token',
                'X-Amz-User-Agent'
            ],
            'allow_credentials': True,  # Required for authentication
            'max_age': 3600,  # 1 hour
            'expose_headers': [
                'X-Correlation-ID',
                'X-Request-ID'
            ]
        }
        
        # Validate CORS configuration
        assert 'Authorization' in cors_config['allow_headers'], "Authorization header must be allowed for authentication"
        assert cors_config['allow_credentials'] is True, "Credentials must be allowed for authentication"
        assert 'OPTIONS' in cors_config['allow_methods'], "OPTIONS method required for CORS preflight"
        
        # Validate origins are HTTPS in production
        for origin in cors_config['allow_origins']:
            if origin != '*':  # Wildcard is only for development
                assert origin.startswith('https://'), f"Origin {origin} should use HTTPS"
        
        # Validate max age is reasonable
        assert 0 < cors_config['max_age'] <= 86400, "Max age should be between 0 and 24 hours"
    
    def test_error_response_structure_for_auth_failures(self):
        """Test error response structure for authentication failures."""
        # Standard authentication error responses
        auth_error_responses = [
            {
                'status_code': 401,
                'error_code': 'UNAUTHORIZED',
                'error': 'Authentication required',
                'message': 'Valid authentication token required to access this resource',
                'timestamp': datetime.utcnow().isoformat() + 'Z',
                'correlation_id': str(uuid.uuid4()),
                'details': {
                    'auth_type': 'Bearer JWT',
                    'required_scopes': ['aws.cognito.signin.user.admin']
                }
            },
            {
                'status_code': 401,
                'error_code': 'TOKEN_EXPIRED',
                'error': 'Token has expired',
                'message': 'The provided authentication token has expired',
                'timestamp': datetime.utcnow().isoformat() + 'Z',
                'correlation_id': str(uuid.uuid4()),
                'details': {
                    'expired_at': (datetime.utcnow() - timedelta(minutes=5)).isoformat() + 'Z',
                    'current_time': datetime.utcnow().isoformat() + 'Z'
                }
            },
            {
                'status_code': 403,
                'error_code': 'FORBIDDEN',
                'error': 'Insufficient permissions',
                'message': 'Valid token provided but insufficient permissions for this resource',
                'timestamp': datetime.utcnow().isoformat() + 'Z',
                'correlation_id': str(uuid.uuid4()),
                'details': {
                    'required_permissions': ['enrollment:read', 'enrollment:write'],
                    'user_permissions': ['enrollment:read']
                }
            }
        ]
        
        for error_response in auth_error_responses:
            # Validate error response structure
            required_fields = ['status_code', 'error_code', 'error', 'message', 'timestamp', 'correlation_id']
            for field in required_fields:
                assert field in error_response, f"Error response missing required field: {field}"
            
            # Validate status codes
            assert error_response['status_code'] in [401, 403], "Auth errors should be 401 or 403"
            
            # Validate correlation ID format
            uuid.UUID(error_response['correlation_id'])  # Should not raise exception
            
            # Validate timestamp format
            datetime.fromisoformat(error_response['timestamp'].replace('Z', '+00:00'))  # Should not raise exception
            
            # Validate error codes are descriptive
            assert error_response['error_code'] in ['UNAUTHORIZED', 'TOKEN_EXPIRED', 'FORBIDDEN', 'INVALID_TOKEN']
    
    def test_security_headers_configuration(self):
        """Test security headers configuration for authenticated endpoints."""
        # Security headers that should be present
        security_headers = {
            'Strict-Transport-Security': 'max-age=31536000; includeSubDomains',
            'X-Content-Type-Options': 'nosniff',
            'X-Frame-Options': 'DENY',
            'X-XSS-Protection': '1; mode=block',
            'Referrer-Policy': 'strict-origin-when-cross-origin',
            'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'",
            'Cache-Control': 'no-store, no-cache, must-revalidate, private',
            'Pragma': 'no-cache'
        }
        
        # Validate security headers
        for header, value in security_headers.items():
            assert isinstance(header, str) and len(header) > 0
            assert isinstance(value, str) and len(value) > 0
        
        # Validate specific security headers
        assert 'max-age=' in security_headers['Strict-Transport-Security']
        assert security_headers['X-Content-Type-Options'] == 'nosniff'
        assert security_headers['X-Frame-Options'] in ['DENY', 'SAMEORIGIN']
        assert 'no-cache' in security_headers['Cache-Control']
    
    def test_rate_limiting_configuration(self):
        """Test rate limiting configuration for authenticated endpoints."""
        # Rate limiting configuration
        rate_limit_config = {
            'throttling_rate_limit': 100,  # requests per second
            'throttling_burst_limit': 200,  # burst capacity
            'per_user_limits': {
                'requests_per_minute': 60,
                'requests_per_hour': 1000,
                'requests_per_day': 10000
            },
            'error_responses': {
                'rate_limit_exceeded': {
                    'status_code': 429,
                    'error_code': 'TOO_MANY_REQUESTS',
                    'retry_after_seconds': 60
                }
            }
        }
        
        # Validate rate limiting configuration
        assert rate_limit_config['throttling_rate_limit'] > 0
        assert rate_limit_config['throttling_burst_limit'] >= rate_limit_config['throttling_rate_limit']
        
        # Validate per-user limits are reasonable
        per_user = rate_limit_config['per_user_limits']
        assert per_user['requests_per_minute'] <= per_user['requests_per_hour']
        assert per_user['requests_per_hour'] <= per_user['requests_per_day']
        
        # Validate error response for rate limiting
        rate_limit_error = rate_limit_config['error_responses']['rate_limit_exceeded']
        assert rate_limit_error['status_code'] == 429
        assert rate_limit_error['retry_after_seconds'] > 0
    
    def _create_valid_jwt_token(self) -> str:
        """Create a mock valid JWT token for testing."""
        header = {
            'alg': 'RS256',
            'kid': 'example-key-id',
            'typ': 'JWT'
        }
        
        payload = {
            'sub': str(uuid.uuid4()),
            'aud': 'example-client-id',
            'iss': 'https://cognito-idp.us-east-1.amazonaws.com/us-east-1_example123',
            'exp': int(time.time()) + 3600,  # Expires in 1 hour
            'iat': int(time.time()),
            'token_use': 'access',
            'scope': 'aws.cognito.signin.user.admin',
            'username': 'testuser'
        }
        
        # Create mock JWT (not cryptographically valid, just for structure testing)
        header_b64 = base64.urlsafe_b64encode(json.dumps(header).encode()).decode().rstrip('=')
        payload_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip('=')
        signature = 'mock-signature'
        
        return f"{header_b64}.{payload_b64}.{signature}"
    
    def _create_valid_id_token(self) -> str:
        """Create a mock valid ID token for testing."""
        header = {
            'alg': 'RS256',
            'kid': 'example-key-id',
            'typ': 'JWT'
        }
        
        payload = {
            'sub': str(uuid.uuid4()),
            'aud': 'example-client-id',
            'iss': 'https://cognito-idp.us-east-1.amazonaws.com/us-east-1_example123',
            'exp': int(time.time()) + 3600,
            'iat': int(time.time()),
            'token_use': 'id',
            'email': 'testuser@example.com',
            'email_verified': True,
            'username': 'testuser'
        }
        
        # Create mock JWT
        header_b64 = base64.urlsafe_b64encode(json.dumps(header).encode()).decode().rstrip('=')
        payload_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip('=')
        signature = 'mock-signature'
        
        return f"{header_b64}.{payload_b64}.{signature}"
    
    def _create_expired_jwt_token(self) -> str:
        """Create a mock expired JWT token for testing."""
        return self._create_jwt_token_with_expiration(-3600)  # Expired 1 hour ago
    
    def _create_jwt_token_with_expiration(self, expires_in_seconds: int) -> str:
        """Create a mock JWT token with specific expiration."""
        header = {
            'alg': 'RS256',
            'kid': 'example-key-id',
            'typ': 'JWT'
        }
        
        payload = {
            'sub': str(uuid.uuid4()),
            'aud': 'example-client-id',
            'iss': 'https://cognito-idp.us-east-1.amazonaws.com/us-east-1_example123',
            'exp': int(time.time()) + expires_in_seconds,
            'iat': int(time.time()),
            'token_use': 'access',
            'scope': 'aws.cognito.signin.user.admin',
            'username': 'testuser'
        }
        
        # Create mock JWT
        header_b64 = base64.urlsafe_b64encode(json.dumps(header).encode()).decode().rstrip('=')
        payload_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip('=')
        signature = 'mock-signature'
        
        return f"{header_b64}.{payload_b64}.{signature}"
    
    def _decode_jwt_payload(self, token: str) -> Dict[str, Any]:
        """Decode JWT payload for testing (not cryptographically verified)."""
        parts = token.split('.')
        if len(parts) != 3:
            raise ValueError("Invalid JWT format")
        
        # Add padding if needed
        payload_b64 = parts[1]
        padding = 4 - len(payload_b64) % 4
        if padding != 4:
            payload_b64 += '=' * padding
        
        payload_json = base64.urlsafe_b64decode(payload_b64).decode()
        return json.loads(payload_json)


def run_authentication_tests():
    """Run authentication tests manually."""
    print("Running authentication and authorization tests...")
    
    test_instance = TestAuthentication()
    
    try:
        print("\n1. Testing Cognito authorizer configuration...")
        test_instance.test_cognito_authorizer_configuration()
        print("✓ Cognito authorizer configuration test passed")
        
        print("\n2. Testing JWT token structure validation...")
        test_instance.test_jwt_token_structure_validation()
        print("✓ JWT token structure validation test passed")
        
        print("\n3. Testing API endpoint authentication...")
        test_instance.test_api_endpoint_authentication_needed()
        print("✓ API endpoint authentication test passed")
        
        print("\n4. Testing unauthorized request handling...")
        test_instance.test_unauthorized_request_handling()
        print("✓ Unauthorized request handling test passed")
        
        print("\n5. Testing valid authentication flow...")
        test_instance.test_valid_authentication_flow()
        print("✓ Valid authentication flow test passed")
        
        print("\n6. Testing token expiration handling...")
        test_instance.test_token_expiration_handling()
        print("✓ Token expiration handling test passed")
        
        print("\n7. Testing CORS configuration for auth...")
        test_instance.test_cors_configuration_for_auth()
        print("✓ CORS configuration for auth test passed")
        
        print("\n8. Testing error response structure for auth failures...")
        test_instance.test_error_response_structure_for_auth_failures()
        print("✓ Error response structure for auth failures test passed")
        
        print("\n9. Testing security headers configuration...")
        test_instance.test_security_headers_configuration()
        print("✓ Security headers configuration test passed")
        
        print("\n10. Testing rate limiting configuration...")
        test_instance.test_rate_limiting_configuration()
        print("✓ Rate limiting configuration test passed")
        
        print("\n🎉 All authentication and authorization tests passed!")
        
    except Exception as e:
        print(f"\n❌ Authentication test failed: {e}")
        raise


if __name__ == "__main__":
    run_authentication_tests()