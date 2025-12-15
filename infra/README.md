# Georgia Tech Enrollment Cloud Backend

AWS CDK infrastructure for the Georgia Tech enrollment data processing system.

## Prerequisites

- Node.js 18+ and npm
- AWS CLI configured with appropriate credentials
- AWS CDK CLI installed globally: `npm install -g aws-cdk`

## Setup

1. Install dependencies:
   ```bash
   npm install
   ```

2. Copy environment configuration:
   ```bash
   cp .env.template .env
   ```

3. Update `.env` with your AWS account details and Cognito configuration:
   - `AWS_ACCOUNT_ID`: Your AWS account ID
   - `AWS_REGION`: Target AWS region (default: us-east-1)
   - `COGNITO_USER_POOL_ID`: Existing Cognito User Pool ID
   - `COGNITO_USER_POOL_CLIENT_ID`: Existing Cognito User Pool Client ID

## Development

- `npm run build`: Compile TypeScript to JavaScript
- `npm run watch`: Watch for changes and compile
- `npm run test`: Run unit tests
- `npm run cdk diff`: Compare deployed stack with current state
- `npm run cdk synth`: Emit the synthesized CloudFormation template

## Deployment

1. Bootstrap CDK (first time only):
   ```bash
   npm run bootstrap
   ```

2. Deploy the stack:
   ```bash
   npm run deploy
   ```

3. Destroy the stack (when needed):
   ```bash
   npm run destroy
   ```

## Environment Variables

### Required
- `COGNITO_USER_POOL_ID`: Existing Cognito User Pool for authentication
- `COGNITO_USER_POOL_CLIENT_ID`: Client ID for the User Pool

### Optional
- `CUSTOM_DOMAIN_NAME`: Custom domain for API Gateway
- `SSL_CERTIFICATE_ARN`: ACM certificate ARN for custom domain
- `HOSTED_ZONE_ID`: Route 53 hosted zone ID for custom domain
- `ENVIRONMENT`: Deployment environment (default: dev)

## Architecture

The system deploys the following AWS resources:
- API Gateway for REST endpoints
- Lambda functions for data processing
- S3 bucket for file storage and job status
- CloudFront distribution for client hosting
- IAM roles and policies for secure access

## Security

- All API endpoints are protected by Cognito authentication
- Lambda functions use least-privilege IAM roles
- S3 bucket configured with appropriate access policies
- CloudFront distribution uses HTTPS only