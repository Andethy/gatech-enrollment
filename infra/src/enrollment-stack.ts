import * as cdk from 'aws-cdk-lib';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as s3deploy from 'aws-cdk-lib/aws-s3-deployment';
import * as cloudfront from 'aws-cdk-lib/aws-cloudfront';
import * as origins from 'aws-cdk-lib/aws-cloudfront-origins';
import * as acm from 'aws-cdk-lib/aws-certificatemanager';
import * as route53 from 'aws-cdk-lib/aws-route53';
import * as targets from 'aws-cdk-lib/aws-route53-targets';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as apigateway from 'aws-cdk-lib/aws-apigateway';
import * as cognito from 'aws-cdk-lib/aws-cognito';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as logs from 'aws-cdk-lib/aws-logs';
import * as sqs from 'aws-cdk-lib/aws-sqs';
import * as lambdaEventSources from 'aws-cdk-lib/aws-lambda-event-sources';
import { Construct } from 'constructs';
import * as path from 'path';

export interface StackConfig {
  cognitoUserPoolId: string;
  cognitoUserPoolClientId: string;
  customDomainName?: string;
  certificateArn?: string;
  hostedZoneId?: string;
  environment: string;
  frontendDomain?: string;
  apiDomain?: string;
}

export interface GatechEnrollmentStackProps extends cdk.StackProps {
  stackConfig: StackConfig;
}

export class EnrollmentStack extends cdk.Stack {
  public readonly fileStorageBucket: s3.Bucket;
  public readonly clientBucket: s3.Bucket;
  public readonly cloudFrontDistribution: cloudfront.Distribution;
  public readonly api: apigateway.RestApi;
  public readonly dataProcessingFunction: lambda.Function;
  public readonly processingQueue: sqs.Queue;
  // PDF processing removed - capacity data is processed at deployment time
  private _cognitoAuthorizer?: apigateway.CognitoUserPoolsAuthorizer;
  private enrollmentGenerateResource?: apigateway.Resource;
  private jobStatusResource?: apigateway.Resource;
  private capacityDataResource?: apigateway.Resource;

  constructor(scope: Construct, id: string, props: GatechEnrollmentStackProps) {
    super(scope, id, props);

    const { stackConfig } = props;

    // Validate required environment variables
    this.validateConfig(stackConfig);

    // Create S3 bucket for file storage
    this.fileStorageBucket = this.createFileStorageBucket(stackConfig);

    // Create S3 bucket and CloudFront distribution for client hosting
    this.clientBucket = this.createClientBucket(stackConfig);
    this.cloudFrontDistribution = this.createCloudFrontDistribution(stackConfig);

    // Deploy client files automatically
    this.deployClientFiles(stackConfig);

    // Create API Gateway with Cognito authentication
    this.api = this.createApiGateway(stackConfig);

    // Set up custom domains and DNS records
    this.setupCustomDomains(stackConfig);

    // Create SQS queue for async processing
    this.processingQueue = this.createProcessingQueue(stackConfig);

    // Create Lambda function for data processing
    this.dataProcessingFunction = this.createDataProcessingFunction(stackConfig);

    // Upload pre-processed capacity data to S3
    this.uploadCapacityData(stackConfig);

    // Create API Gateway method integrations
    this.createApiIntegrations(stackConfig);

    // Output important values
    new cdk.CfnOutput(this, 'Environment', {
      value: stackConfig.environment,
      description: 'Deployment environment',
    });

    new cdk.CfnOutput(this, 'Region', {
      value: this.region,
      description: 'AWS region for deployment',
    });

    new cdk.CfnOutput(this, 'FileStorageBucketName', {
      value: this.fileStorageBucket.bucketName,
      description: 'S3 bucket for storing CSV files, job status, and room capacity data',
    });

    new cdk.CfnOutput(this, 'FileStorageBucketArn', {
      value: this.fileStorageBucket.bucketArn,
      description: 'ARN of the file storage S3 bucket',
    });

    new cdk.CfnOutput(this, 'ClientBucketName', {
      value: this.clientBucket.bucketName,
      description: 'S3 bucket for hosting client build files',
    });

    new cdk.CfnOutput(this, 'CloudFrontDistributionId', {
      value: this.cloudFrontDistribution.distributionId,
      description: 'CloudFront distribution ID for client hosting',
    });

    new cdk.CfnOutput(this, 'CloudFrontDomainName', {
      value: this.cloudFrontDistribution.distributionDomainName,
      description: 'CloudFront distribution domain name',
    });

    if (stackConfig.frontendDomain) {
      new cdk.CfnOutput(this, 'FrontendCustomDomain', {
        value: stackConfig.frontendDomain,
        description: 'Custom domain name for the client application',
      });
    }

    if (stackConfig.apiDomain) {
      new cdk.CfnOutput(this, 'ApiCustomDomainName', {
        value: stackConfig.apiDomain,
        description: 'Custom domain name for the API',
      });
    }

    new cdk.CfnOutput(this, 'ApiGatewayUrl', {
      value: this.api.url,
      description: 'API Gateway endpoint URL',
    });

    new cdk.CfnOutput(this, 'ApiGatewayId', {
      value: this.api.restApiId,
      description: 'API Gateway REST API ID',
    });

    new cdk.CfnOutput(this, 'CognitoUserPoolId', {
      value: stackConfig.cognitoUserPoolId,
      description: 'Cognito User Pool ID used for authentication',
    });

    new cdk.CfnOutput(this, 'CognitoUserPoolClientId', {
      value: stackConfig.cognitoUserPoolClientId,
      description: 'Cognito User Pool Client ID for authentication',
    });

    new cdk.CfnOutput(this, 'DataProcessingFunctionName', {
      value: this.dataProcessingFunction.functionName,
      description: 'Name of the data processing Lambda function',
    });

    new cdk.CfnOutput(this, 'DataProcessingFunctionArn', {
      value: this.dataProcessingFunction.functionArn,
      description: 'ARN of the data processing Lambda function',
    });

    new cdk.CfnOutput(this, 'CapacityDataLocation', {
      value: `s3://${this.fileStorageBucket.bucketName}/capacity-data/room_capacity_data.csv`,
      description: 'S3 location of pre-processed room capacity data',
    });
  }

  private createFileStorageBucket(config: StackConfig): s3.Bucket {
    // Create S3 bucket for storing CSV files, job status, and room capacity data
    const bucket = new s3.Bucket(this, 'FileStorageBucket', {
      bucketName: `gatech-enrollment-${config.environment}-${this.account}`,
      versioned: false,
      publicReadAccess: false,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      encryption: s3.BucketEncryption.S3_MANAGED,
      lifecycleRules: [
        {
          id: 'DeleteOldFiles',
          enabled: true,
          expiration: cdk.Duration.days(30), // Clean up files after 30 days
          prefix: 'generated-files/',
        },
        {
          id: 'DeleteOldJobStatus',
          enabled: true,
          expiration: cdk.Duration.days(7), // Clean up job status after 7 days
          prefix: 'job-status/',
        },
      ],
      cors: [
        {
          allowedMethods: [
            s3.HttpMethods.GET,
            s3.HttpMethods.POST,
            s3.HttpMethods.PUT,
            s3.HttpMethods.DELETE,
            s3.HttpMethods.HEAD,
          ],
          allowedOrigins: ['*'], // Will be restricted to specific domains in production
          allowedHeaders: ['*'],
          exposedHeaders: [
            'ETag',
            'x-amz-meta-custom-header',
          ],
          maxAge: 3000,
        },
      ],
      removalPolicy: config.environment === 'prod' 
        ? cdk.RemovalPolicy.RETAIN 
        : cdk.RemovalPolicy.DESTROY,
    });

    // Add bucket policy for Lambda access (will be refined when Lambda functions are created)
    const bucketPolicy = new iam.PolicyStatement({
      sid: 'AllowLambdaAccess',
      effect: iam.Effect.ALLOW,
      principals: [new iam.ServicePrincipal('lambda.amazonaws.com')],
      actions: [
        's3:GetObject',
        's3:PutObject',
        's3:DeleteObject',
        's3:ListBucket',
      ],
      resources: [
        bucket.bucketArn,
        `${bucket.bucketArn}/*`,
      ],
      conditions: {
        StringEquals: {
          'aws:SourceAccount': this.account,
        },
      },
    });

    bucket.addToResourcePolicy(bucketPolicy);

    return bucket;
  }

  private createClientBucket(config: StackConfig): s3.Bucket {
    // Create S3 bucket for hosting client build files
    const clientBucket = new s3.Bucket(this, 'ClientBucket', {
      bucketName: `gatech-enrollment-client-${config.environment}-${this.account}`,
      versioned: false,
      publicReadAccess: false,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      encryption: s3.BucketEncryption.S3_MANAGED,
      removalPolicy: config.environment === 'prod' 
        ? cdk.RemovalPolicy.RETAIN 
        : cdk.RemovalPolicy.DESTROY,
    });

    return clientBucket;
  }

  private createCloudFrontDistribution(config: StackConfig): cloudfront.Distribution {
    // Create Origin Access Control for S3
    const originAccessControl = new cloudfront.S3OriginAccessControl(this, 'ClientOAC', {
      description: 'OAC for client bucket access',
    });

    // Create cache policy for static assets
    const staticAssetsCachePolicy = new cloudfront.CachePolicy(this, 'StaticAssetsCachePolicy', {
      cachePolicyName: `gatech-enrollment-static-${config.environment}`,
      comment: 'Cache policy for static assets (JS, CSS, images)',
      defaultTtl: cdk.Duration.days(1),
      maxTtl: cdk.Duration.days(365),
      minTtl: cdk.Duration.seconds(0),
      headerBehavior: cloudfront.CacheHeaderBehavior.none(),
      queryStringBehavior: cloudfront.CacheQueryStringBehavior.none(),
      cookieBehavior: cloudfront.CacheCookieBehavior.none(),
    });

    // Create cache policy for HTML files
    const htmlCachePolicy = new cloudfront.CachePolicy(this, 'HtmlCachePolicy', {
      cachePolicyName: `gatech-enrollment-html-${config.environment}`,
      comment: 'Cache policy for HTML files with shorter TTL',
      defaultTtl: cdk.Duration.minutes(5),
      maxTtl: cdk.Duration.hours(1),
      minTtl: cdk.Duration.seconds(0),
      headerBehavior: cloudfront.CacheHeaderBehavior.none(),
      queryStringBehavior: cloudfront.CacheQueryStringBehavior.none(),
      cookieBehavior: cloudfront.CacheCookieBehavior.none(),
    });

    // Get SSL certificate if custom domain is configured
    let certificate: acm.ICertificate | undefined;
    if (config.certificateArn) {
      certificate = acm.Certificate.fromCertificateArn(
        this,
        'SslCertificate',
        config.certificateArn
      );
    }

    // Create CloudFront distribution
    const distribution = new cloudfront.Distribution(this, 'ClientDistribution', {
      comment: `Georgia Tech Enrollment Client - ${config.environment}`,
      defaultRootObject: 'index.html',
      domainNames: config.frontendDomain ? [config.frontendDomain] : undefined,
      certificate: certificate,
      minimumProtocolVersion: cloudfront.SecurityPolicyProtocol.TLS_V1_2_2021,
      httpVersion: cloudfront.HttpVersion.HTTP2_AND_3,
      priceClass: cloudfront.PriceClass.PRICE_CLASS_100, // Use only North America and Europe
      enableIpv6: true,
      defaultBehavior: {
        origin: origins.S3BucketOrigin.withOriginAccessControl(this.clientBucket, {
          originAccessControl: originAccessControl,
        }),
        viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
        cachePolicy: htmlCachePolicy,
        compress: true,
        allowedMethods: cloudfront.AllowedMethods.ALLOW_GET_HEAD,
      },
      additionalBehaviors: {
        '/static/*': {
          origin: origins.S3BucketOrigin.withOriginAccessControl(this.clientBucket, {
            originAccessControl: originAccessControl,
          }),
          viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
          cachePolicy: staticAssetsCachePolicy,
          compress: true,
          allowedMethods: cloudfront.AllowedMethods.ALLOW_GET_HEAD,
        },
        '*.js': {
          origin: origins.S3BucketOrigin.withOriginAccessControl(this.clientBucket, {
            originAccessControl: originAccessControl,
          }),
          viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
          cachePolicy: staticAssetsCachePolicy,
          compress: true,
          allowedMethods: cloudfront.AllowedMethods.ALLOW_GET_HEAD,
        },
        '*.css': {
          origin: origins.S3BucketOrigin.withOriginAccessControl(this.clientBucket, {
            originAccessControl: originAccessControl,
          }),
          viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
          cachePolicy: staticAssetsCachePolicy,
          compress: true,
          allowedMethods: cloudfront.AllowedMethods.ALLOW_GET_HEAD,
        },
      },
      errorResponses: [
        {
          httpStatus: 404,
          responseHttpStatus: 200,
          responsePagePath: '/index.html',
          ttl: cdk.Duration.minutes(5),
        },
        {
          httpStatus: 403,
          responseHttpStatus: 200,
          responsePagePath: '/index.html',
          ttl: cdk.Duration.minutes(5),
        },
      ],
    });

    // Grant CloudFront access to the client bucket
    this.clientBucket.addToResourcePolicy(
      new iam.PolicyStatement({
        sid: 'AllowCloudFrontServicePrincipal',
        effect: iam.Effect.ALLOW,
        principals: [new iam.ServicePrincipal('cloudfront.amazonaws.com')],
        actions: ['s3:GetObject'],
        resources: [`${this.clientBucket.bucketArn}/*`],
        conditions: {
          StringEquals: {
            'AWS:SourceArn': `arn:aws:cloudfront::${this.account}:distribution/${distribution.distributionId}`,
          },
        },
      })
    );

    return distribution;
  }

  private createApiGateway(config: StackConfig): apigateway.RestApi {
    // Create API Gateway REST API
    const api = new apigateway.RestApi(this, 'EnrollmentApi', {
      restApiName: `gatech-enrollment-api-${config.environment}`,
      description: `Georgia Tech Enrollment Data API - ${config.environment}`,
      deploy: true, // Simple deployment without staging
      deployOptions: {
        throttlingRateLimit: 100,
        throttlingBurstLimit: 200,
        loggingLevel: apigateway.MethodLoggingLevel.INFO,
        dataTraceEnabled: config.environment !== 'prod', // Disable in production
        metricsEnabled: true,
      },
      defaultCorsPreflightOptions: {
        allowOrigins: config.environment === 'prod' 
          ? [config.customDomainName ? `https://${config.customDomainName}` : 'https://localhost:3000']
          : apigateway.Cors.ALL_ORIGINS,
        allowMethods: ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'],
        allowHeaders: [
          'Content-Type',
          'X-Amz-Date',
          'Authorization',
          'X-Api-Key',
          'X-Amz-Security-Token',
          'X-Amz-User-Agent',
        ],
        allowCredentials: true,
        maxAge: cdk.Duration.hours(1),
      },
      binaryMediaTypes: ['multipart/form-data', 'application/pdf'],
      // No policy - allow all access by default
    });

    // Create API resource structure
    const apiV1 = api.root.addResource('api').addResource('v1');
    
    // Enrollment endpoints
    const enrollmentResource = apiV1.addResource('enrollment');
    this.enrollmentGenerateResource = enrollmentResource.addResource('generate'); // POST /api/v1/enrollment/generate
    
    // Job management endpoints
    const jobsResource = apiV1.addResource('jobs');
    const jobResource = jobsResource.addResource('{jobId}');
    this.jobStatusResource = jobResource.addResource('status'); // GET /api/v1/jobs/{jobId}/status
    
    // Capacity data endpoint (upload removed - data is pre-processed)
    const capacityResource = apiV1.addResource('capacity');
    this.capacityDataResource = capacityResource.addResource('data'); // GET /api/v1/capacity/data

    // Custom domain setup is handled in setupCustomDomains() method

    return api;
  }

  private createCognitoAuthorizer(config: StackConfig, api: apigateway.RestApi): apigateway.CognitoUserPoolsAuthorizer {
    // Import existing Cognito User Pool
    const userPool = cognito.UserPool.fromUserPoolId(
      this,
      'ExistingUserPool',
      config.cognitoUserPoolId
    );

    // Note: User Pool Client ID is stored in config for client applications

    // Create Cognito authorizer for API Gateway
    const authorizer = new apigateway.CognitoUserPoolsAuthorizer(this, 'CognitoAuthorizer', {
      cognitoUserPools: [userPool],
      authorizerName: `gatech-enrollment-authorizer-${config.environment}`,
      identitySource: 'method.request.header.Authorization',
      resultsCacheTtl: cdk.Duration.minutes(5),
    });

    // Add validation for JWT token format
    authorizer.node.addMetadata('tokenValidation', {
      validateTokenFormat: true,
      validateTokenExpiration: true,
      validateTokenSignature: true,
    });

    return authorizer;
  }

  // Helper method to apply authentication to API methods
  public addAuthenticatedMethod(
    resource: apigateway.Resource,
    httpMethod: string,
    integration: apigateway.Integration,
    config: StackConfig,
    options?: apigateway.MethodOptions
  ): apigateway.Method {
    const authorizer = this.createCognitoAuthorizerIfNeeded(config);
    
    return resource.addMethod(httpMethod, integration, {
      ...options,
      authorizer: authorizer,
      authorizationType: apigateway.AuthorizationType.COGNITO,
      requestValidator: new apigateway.RequestValidator(this, `${resource.node.id}${httpMethod}Validator`, {
        restApi: this.api,
        requestValidatorName: `${resource.node.id}-${httpMethod}-validator`,
        validateRequestBody: httpMethod === 'POST' || httpMethod === 'PUT',
        validateRequestParameters: true,
      }),
    });
  }

  // Lazy getter for Cognito authorizer
  public get cognitoAuthorizer(): apigateway.CognitoUserPoolsAuthorizer {
    if (!this._cognitoAuthorizer) {
      throw new Error('Cognito authorizer not initialized. Call createCognitoAuthorizer() first.');
    }
    return this._cognitoAuthorizer;
  }

  // Method to create the Cognito authorizer when needed
  public createCognitoAuthorizerIfNeeded(config: StackConfig): apigateway.CognitoUserPoolsAuthorizer {
    if (!this._cognitoAuthorizer) {
      this._cognitoAuthorizer = this.createCognitoAuthorizer(config, this.api);
    }
    return this._cognitoAuthorizer;
  }

  private createProcessingQueue(config: StackConfig): sqs.Queue {
    // Create DLQ for failed messages
    const deadLetterQueue = new sqs.Queue(this, 'ProcessingDeadLetterQueue', {
      queueName: `gatech-enrollment-dlq-${config.environment}`,
      retentionPeriod: cdk.Duration.days(14),
    });

    // Create main processing queue
    const processingQueue = new sqs.Queue(this, 'ProcessingQueue', {
      queueName: `gatech-enrollment-processing-${config.environment}`,
      visibilityTimeout: cdk.Duration.minutes(15), // Match Lambda timeout
      retentionPeriod: cdk.Duration.days(4),
      deadLetterQueue: {
        queue: deadLetterQueue,
        maxReceiveCount: 3, // Retry failed jobs 3 times
      },
      // Prevent runaway scaling
      receiveMessageWaitTime: cdk.Duration.seconds(20), // Long polling
    });

    return processingQueue;
  }

  private createDataProcessingFunction(config: StackConfig): lambda.Function {
    // Create IAM role for the Lambda function
    const lambdaRole = new iam.Role(this, 'DataProcessingLambdaRole', {
      assumedBy: new iam.ServicePrincipal('lambda.amazonaws.com'),
      description: 'IAM role for data processing Lambda function',
      managedPolicies: [
        iam.ManagedPolicy.fromAwsManagedPolicyName('service-role/AWSLambdaBasicExecutionRole'),
      ],
      inlinePolicies: {
        S3Access: new iam.PolicyDocument({
          statements: [
            new iam.PolicyStatement({
              effect: iam.Effect.ALLOW,
              actions: [
                's3:GetObject',
                's3:PutObject',
                's3:DeleteObject',
                's3:ListBucket',
              ],
              resources: [
                this.fileStorageBucket.bucketArn,
                `${this.fileStorageBucket.bucketArn}/*`,
              ],
            }),
          ],
        }),
        CloudWatchLogs: new iam.PolicyDocument({
          statements: [
            new iam.PolicyStatement({
              effect: iam.Effect.ALLOW,
              actions: [
                'logs:CreateLogGroup',
                'logs:CreateLogStream',
                'logs:PutLogEvents',
                'logs:DescribeLogStreams',
                'logs:DescribeLogGroups',
              ],
              resources: ['*'],
            }),
          ],
        }),
        SQSAccess: new iam.PolicyDocument({
          statements: [
            new iam.PolicyStatement({
              effect: iam.Effect.ALLOW,
              actions: [
                'sqs:SendMessage',
                'sqs:ReceiveMessage',
                'sqs:DeleteMessage',
                'sqs:GetQueueAttributes',
              ],
              resources: [
                this.processingQueue.queueArn,
              ],
            }),
          ],
        }),
      },
    });

    // Create CloudWatch log group with retention policy
    const logGroup = new logs.LogGroup(this, 'DataProcessingLogGroup', {
      logGroupName: `/aws/lambda/gatech-enrollment-data-processing-${config.environment}`,
      retention: config.environment === 'prod' 
        ? logs.RetentionDays.ONE_MONTH 
        : logs.RetentionDays.ONE_WEEK,
      removalPolicy: config.environment === 'prod' 
        ? cdk.RemovalPolicy.RETAIN 
        : cdk.RemovalPolicy.DESTROY,
    });

    // Create the Lambda function
    const dataProcessingFunction = new lambda.Function(this, 'DataProcessingFunction', {
      functionName: `gatech-enrollment-data-processing-${config.environment}`,
      description: 'Processes Georgia Tech enrollment data requests and generates CSV reports',
      runtime: lambda.Runtime.PYTHON_3_11,
      handler: 'index.lambda_handler',
      code: lambda.Code.fromAsset(path.join(__dirname, '../lambda/data-processing')),
      layers: [
        // Use AWS managed layer for pandas/numpy (much more reliable)
        lambda.LayerVersion.fromLayerVersionArn(this, 'AWSSDKPandasLayer', 
          'arn:aws:lambda:us-east-1:336392948345:layer:AWSSDKPandas-Python311:16'
        )
      ],
      role: lambdaRole,
      timeout: cdk.Duration.minutes(15), // Maximum timeout for data processing
      memorySize: 1024, // 1GB memory for pandas operations
      environment: {
        S3_BUCKET_NAME: this.fileStorageBucket.bucketName,
        SQS_QUEUE_URL: this.processingQueue.queueUrl,
        ENVIRONMENT: config.environment,
        LOG_LEVEL: config.environment === 'prod' ? 'INFO' : 'DEBUG',
      },
      logGroup: logGroup,
      // Removed reserved concurrency to avoid account limits
      deadLetterQueue: undefined, // Will be added in later tasks if needed
      retryAttempts: 0, // Disable automatic retries for now
    });

    // Grant the Lambda function access to the S3 bucket
    this.fileStorageBucket.grantReadWrite(dataProcessingFunction);

    // Add SQS event source to Lambda function
    dataProcessingFunction.addEventSource(
      new lambdaEventSources.SqsEventSource(this.processingQueue, {
        batchSize: 1, // Process one job at a time
        maxBatchingWindow: cdk.Duration.seconds(5),
        reportBatchItemFailures: true,
      })
    );

    return dataProcessingFunction;
  }

  private uploadCapacityData(config: StackConfig): void {
    // Upload pre-processed capacity data to S3 during deployment
    new s3deploy.BucketDeployment(this, 'CapacityDataDeployment', {
      sources: [s3deploy.Source.asset(path.join(__dirname, '../capacity-data'))],
      destinationBucket: this.fileStorageBucket,
      destinationKeyPrefix: 'capacity-data/',
      prune: false, // Don't delete other files in the bucket
      retainOnDelete: config.environment === 'prod',
    });
  }

  private createApiIntegrations(config: StackConfig): void {
    // Create Lambda integration for data processing function
    const dataProcessingIntegration = new apigateway.LambdaIntegration(this.dataProcessingFunction, {
      requestTemplates: { 'application/json': '{ "statusCode": "200" }' },
      proxy: true, // Use Lambda proxy integration
    });

    // PDF processing removed - capacity data is pre-processed at deployment

    // Ensure we have the required resources
    if (!this.enrollmentGenerateResource) {
      throw new Error('Enrollment generate resource not found');
    }
    if (!this.jobStatusResource) {
      throw new Error('Job status resource not found');
    }

    // Add POST /api/v1/enrollment/generate method (no authentication for now)
    this.enrollmentGenerateResource.addMethod('POST', dataProcessingIntegration, {
      // Removed complex request model validation to avoid schema issues
      // Validation is handled in the Lambda function instead
      methodResponses: [
        {
          statusCode: '202',
          responseModels: {
            'application/json': apigateway.Model.EMPTY_MODEL,
          },
        },
        {
          statusCode: '400',
          responseModels: {
            'application/json': apigateway.Model.ERROR_MODEL,
          },
        },
        {
          statusCode: '500',
          responseModels: {
            'application/json': apigateway.Model.ERROR_MODEL,
          },
        },
      ],
    });

    // Add GET /api/v1/jobs/{jobId}/status method | TODO: AUTH
    this.jobStatusResource.addMethod('GET', dataProcessingIntegration, {
      requestParameters: {
        'method.request.path.jobId': true,
      },
      methodResponses: [
        {
          statusCode: '200',
          responseModels: {
            'application/json': new apigateway.Model(this, 'JobStatusModel', {
              restApi: this.api,
              modelName: 'JobStatusResponse',
              description: 'Model for job status response',
              schema: {
                type: apigateway.JsonSchemaType.OBJECT,
                properties: {
                  job_id: {
                    type: apigateway.JsonSchemaType.STRING,
                    description: 'Unique job identifier',
                  },
                  status: {
                    type: apigateway.JsonSchemaType.STRING,
                    enum: ['pending', 'processing', 'completed', 'failed'],
                    description: 'Current job status',
                  },
                  progress: {
                    type: apigateway.JsonSchemaType.NUMBER,
                    minimum: 0,
                    maximum: 1,
                    description: 'Job completion progress (0.0 to 1.0)',
                  },
                  created_at: {
                    type: apigateway.JsonSchemaType.STRING,
                    description: 'Job creation timestamp',
                  },
                  updated_at: {
                    type: apigateway.JsonSchemaType.STRING,
                    description: 'Last update timestamp',
                  },
                  parameters: {
                    type: apigateway.JsonSchemaType.OBJECT,
                    description: 'Original request parameters',
                  },
                  files: {
                    type: apigateway.JsonSchemaType.ARRAY,
                    items: {
                      type: apigateway.JsonSchemaType.OBJECT,
                      properties: {
                        filename: {
                          type: apigateway.JsonSchemaType.STRING,
                        },
                        download_url: {
                          type: apigateway.JsonSchemaType.STRING,
                        },
                        size_bytes: {
                          type: apigateway.JsonSchemaType.INTEGER,
                        },
                        file_type: {
                          type: apigateway.JsonSchemaType.STRING,
                        },
                      },
                    },
                    description: 'Generated files with download URLs',
                  },
                  error_message: {
                    type: apigateway.JsonSchemaType.STRING,
                    description: 'Error message if job failed',
                  },
                },
                required: ['job_id', 'status', 'progress', 'created_at', 'updated_at'],
              },
            }),
          },
        },
        {
          statusCode: '400',
          responseModels: {
            'application/json': apigateway.Model.ERROR_MODEL,
          },
        },
        {
          statusCode: '404',
          responseModels: {
            'application/json': apigateway.Model.ERROR_MODEL,
          },
        },
        {
          statusCode: '500',
          responseModels: {
            'application/json': apigateway.Model.ERROR_MODEL,
          },
        },
      ],
    });

    // Add GET /api/v1/capacity/data method with authentication |  TODO: AUTH
    if (!this.capacityDataResource) {
      throw new Error('Capacity data resource not found');
    }
    
    // Add GET /api/v1/capacity/data method | TODO: AUTH
    this.capacityDataResource.addMethod('GET', dataProcessingIntegration, {
      methodResponses: [
          {
            statusCode: '200',
            responseModels: {
              'application/json': new apigateway.Model(this, 'CapacityDataModel', {
                restApi: this.api,
                modelName: 'CapacityDataResponse',
                description: 'Model for capacity data response',
                schema: {
                  type: apigateway.JsonSchemaType.OBJECT,
                  properties: {
                    download_url: {
                      type: apigateway.JsonSchemaType.STRING,
                      description: 'Presigned URL for downloading capacity data',
                    },
                    filename: {
                      type: apigateway.JsonSchemaType.STRING,
                      description: 'Name of the capacity data file',
                    },
                    last_modified: {
                      type: apigateway.JsonSchemaType.STRING,
                      description: 'Last modification timestamp',
                    },
                    size_bytes: {
                      type: apigateway.JsonSchemaType.INTEGER,
                      description: 'File size in bytes',
                    },
                  },
                  required: ['download_url', 'filename'],
                },
              }),
            },
          },
          {
            statusCode: '404',
            responseModels: {
              'application/json': apigateway.Model.ERROR_MODEL,
            },
          },
          {
            statusCode: '401',
            responseModels: {
              'application/json': apigateway.Model.ERROR_MODEL,
            },
          },
          {
            statusCode: '500',
            responseModels: {
              'application/json': apigateway.Model.ERROR_MODEL,
            },
          },
        ],
      }
    );

    // Grant API Gateway permission to invoke the Lambda functions
    this.dataProcessingFunction.addPermission('ApiGatewayInvoke', {
      principal: new iam.ServicePrincipal('apigateway.amazonaws.com'),
      action: 'lambda:InvokeFunction',
      sourceArn: `${this.api.arnForExecuteApi('*')}`,
    });

    // PDF processing Lambda removed - capacity data handled by data processing Lambda
  }

  private deployClientFiles(config: StackConfig): void {
    // Deploy client files to S3 during CDK deployment
    new s3deploy.BucketDeployment(this, 'ClientDeployment', {
      sources: [s3deploy.Source.asset(path.join(__dirname, '../../client/dist'))],
      destinationBucket: this.clientBucket,
      distribution: this.cloudFrontDistribution,
      distributionPaths: ['/*'], // Invalidate all paths
      prune: true, // Remove old files
      retainOnDelete: config.environment === 'prod',
      memoryLimit: 512,
    });
  }

  private setupCustomDomains(config: StackConfig): void {
    if (!config.frontendDomain && !config.apiDomain) {
      return; // No custom domains configured
    }

    // Note: DNS records are not created automatically since domain is hosted on Namecheap
    // Manual DNS setup required - see stack outputs for target domains

    // Create custom domain for API Gateway
    if (config.apiDomain && config.certificateArn) {
      const certificate = acm.Certificate.fromCertificateArn(
        this,
        'ApiSslCertificate2',
        config.certificateArn
      );

      const apiDomainName = new apigateway.DomainName(this, 'ApiCustomDomainV2', {
        domainName: config.apiDomain,
        certificate: certificate,
        endpointType: apigateway.EndpointType.EDGE,
        securityPolicy: apigateway.SecurityPolicy.TLS_1_2,
      });

      // Map the custom domain to the API Gateway
      new apigateway.BasePathMapping(this, 'ApiBasePathMappingV2', {
        domainName: apiDomainName,
        restApi: this.api,
        stage: this.api.deploymentStage,
      });

      // Output the API domain target for manual DNS setup
      new cdk.CfnOutput(this, 'ApiCustomDomainTarget', {
        value: apiDomainName.domainNameAliasDomainName,
        description: `CNAME target for ${config.apiDomain} (set this in Namecheap DNS)`,
      });
    }

    // Output CloudFront domain target for manual DNS setup
    if (config.frontendDomain) {
      new cdk.CfnOutput(this, 'FrontendCustomDomainTarget', {
        value: this.cloudFrontDistribution.distributionDomainName,
        description: `CNAME target for ${config.frontendDomain} (set this in Namecheap DNS)`,
      });
    }
  }

  // TODO - AUTH
  private validateConfig(config: StackConfig): void {
    // Temporarily removed Cognito validation since we're deploying without auth
    // const requiredFields = [
    //   'cognitoUserPoolId',
    //   'cognitoUserPoolClientId',
    // ];

    // const missingFields = requiredFields.filter(field => !config[field as keyof StackConfig]);
    
    // if (missingFields.length > 0) {
    //   throw new Error(`Missing required environment variables: ${missingFields.join(', ')}`);
    // }
  }
}