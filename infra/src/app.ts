#!/usr/bin/env node
import 'source-map-support/register';
import * as cdk from 'aws-cdk-lib';
import { EnrollmentStack } from './enrollment-stack';
import * as dotenv from 'dotenv';

// Load environment variables from .env file
dotenv.config({ path: __dirname + '/../.env' });

const app = new cdk.App();

// Get environment configuration
const account = process.env.CDK_DEFAULT_ACCOUNT || process.env.AWS_ACCOUNT_ID;
const region = process.env.CDK_DEFAULT_REGION || process.env.AWS_REGION || 'us-east-1';

// Environment configuration
const env = {
  account,
  region,
};

// Stack configuration from environment variables
const stackConfig = {
  cognitoUserPoolId: process.env.COGNITO_USER_POOL_ID || '',
  cognitoUserPoolClientId: process.env.COGNITO_USER_POOL_CLIENT_ID || '',
  customDomainName: process.env.DOMAIN_NAME || '',
  certificateArn: process.env.DOMAIN_CERT || '',
  hostedZoneId: process.env.HOSTED_ZONE_ID || '',
  environment: process.env.ENVIRONMENT || 'dev',
  // Parse domain configuration for frontend and API
  frontendDomain: process.env.DOMAIN_NAME || '',
  apiDomain: process.env.DOMAIN_NAME ? `api.${process.env.DOMAIN_NAME}` : '',
};

// Create the main stack
new EnrollmentStack(app, 'EnrollmentStack', {
  env,
  stackConfig,
  description: 'Georgia Tech Enrollment Data Processing Cloud Backend',
});

// Add tags to all resources
cdk.Tags.of(app).add('Project', 'GatechEnrollment');
cdk.Tags.of(app).add('Environment', stackConfig.environment);