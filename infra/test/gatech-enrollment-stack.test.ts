import * as cdk from 'aws-cdk-lib';
import { Template } from 'aws-cdk-lib/assertions';
import { EnrollmentStack, StackConfig } from '../src/enrollment-stack';

describe('EnrollmentStack', () => {
  let app: cdk.App;
  let stackConfig: StackConfig;

  beforeEach(() => {
    app = new cdk.App();
    stackConfig = {
      cognitoUserPoolId: 'us-east-1_TEST123456',
      cognitoUserPoolClientId: 'test-client-id-123456',
      customDomainName: 'api.test.com',
      certificateArn: 'arn:aws:acm:us-east-1:123456789012:certificate/test',
      hostedZoneId: 'Z123456789',
      environment: 'test',
    };
  });

  test('Stack creates successfully with valid configuration', () => {
    // WHEN
    const stack = new EnrollmentStack(app, 'TestStack', {
      stackConfig,
      env: { account: '123456789012', region: 'us-east-1' },
    });

    // THEN
    const template = Template.fromStack(stack);
    
    // Verify stack can be synthesized without errors
    expect(template).toBeDefined();
  });

  test('Stack throws error with missing required configuration', () => {
    // GIVEN
    const invalidConfig = {
      ...stackConfig,
      cognitoUserPoolId: '',
    };

    // WHEN/THEN
    expect(() => {
      new EnrollmentStack(app, 'TestStack', {
        stackConfig: invalidConfig,
        env: { account: '123456789012', region: 'us-east-1' },
      });
    }).toThrow('Missing required environment variables: cognitoUserPoolId');
  });

  test('Stack outputs include environment and region', () => {
    // WHEN
    const stack = new EnrollmentStack(app, 'TestStack', {
      stackConfig,
      env: { account: '123456789012', region: 'us-east-1' },
    });

    // THEN
    const template = Template.fromStack(stack);
    
    template.hasOutput('Environment', {
      Value: 'test',
      Description: 'Deployment environment',
    });

    template.hasOutput('Region', {
      Value: 'us-east-1',
      Description: 'AWS region for deployment',
    });
  });

  test('Stack creates S3 buckets with proper configuration', () => {
    // WHEN
    const stack = new EnrollmentStack(app, 'TestStack', {
      stackConfig,
      env: { account: '123456789012', region: 'us-east-1' },
    });

    // THEN
    const template = Template.fromStack(stack);
    
    // Verify file storage bucket exists
    template.hasResourceProperties('AWS::S3::Bucket', {
      BucketName: 'gatech-enrollment-test-123456789012',
      BucketEncryption: {
        ServerSideEncryptionConfiguration: [
          {
            ServerSideEncryptionByDefault: {
              SSEAlgorithm: 'AES256',
            },
          },
        ],
      },
    });

    // Verify client bucket exists
    template.hasResourceProperties('AWS::S3::Bucket', {
      BucketName: 'gatech-enrollment-client-test-123456789012',
    });

    // Verify bucket outputs
    template.hasOutput('FileStorageBucketName', {
      Description: 'S3 bucket for storing CSV files, job status, and room capacity data',
    });

    template.hasOutput('ClientBucketName', {
      Description: 'S3 bucket for hosting client build files',
    });
  });

  test('Stack creates CloudFront distribution with proper configuration', () => {
    // WHEN
    const stack = new EnrollmentStack(app, 'TestStack', {
      stackConfig,
      env: { account: '123456789012', region: 'us-east-1' },
    });

    // THEN
    const template = Template.fromStack(stack);
    
    // Verify CloudFront distribution exists
    template.hasResourceProperties('AWS::CloudFront::Distribution', {
      DistributionConfig: {
        Comment: 'Georgia Tech Enrollment Client - test',
        DefaultRootObject: 'index.html',
        Enabled: true,
        HttpVersion: 'http2and3',
        IPV6Enabled: true,
        PriceClass: 'PriceClass_100',
      },
    });

    // Verify Origin Access Control exists
    template.hasResourceProperties('AWS::CloudFront::OriginAccessControl', {
      OriginAccessControlConfig: {
        Description: 'OAC for client bucket access',
        OriginAccessControlOriginType: 's3',
        SigningBehavior: 'always',
        SigningProtocol: 'sigv4',
      },
    });

    // Verify CloudFront outputs
    template.hasOutput('CloudFrontDistributionId', {
      Description: 'CloudFront distribution ID for client hosting',
    });

    template.hasOutput('CloudFrontDomainName', {
      Description: 'CloudFront distribution domain name',
    });
  });

  test('Stack creates API Gateway with proper configuration', () => {
    // WHEN
    const stack = new EnrollmentStack(app, 'TestStack', {
      stackConfig,
      env: { account: '123456789012', region: 'us-east-1' },
    });

    // THEN
    const template = Template.fromStack(stack);
    
    // Verify API Gateway exists
    template.hasResourceProperties('AWS::ApiGateway::RestApi', {
      Name: 'gatech-enrollment-api-test',
      Description: 'Georgia Tech Enrollment Data API - test',
      BinaryMediaTypes: ['multipart/form-data', 'application/pdf'],
    });

    // Verify API Gateway deployment exists (simple deployment without explicit staging)
    template.resourceCountIs('AWS::ApiGateway::Deployment', 1);

    // Verify API Gateway outputs
    template.hasOutput('ApiGatewayUrl', {
      Description: 'API Gateway endpoint URL',
    });

    template.hasOutput('ApiGatewayId', {
      Description: 'API Gateway REST API ID',
    });

    template.hasOutput('CognitoUserPoolId', {
      Value: 'us-east-1_TEST123456',
      Description: 'Cognito User Pool ID used for authentication',
    });

    template.hasOutput('CognitoUserPoolClientId', {
      Value: 'test-client-id-123456',
      Description: 'Cognito User Pool Client ID for authentication',
    });
  });
});