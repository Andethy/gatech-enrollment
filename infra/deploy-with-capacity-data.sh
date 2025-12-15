#!/bin/bash

# Deployment script that processes capacity data and then deploys the CDK stack

set -e

echo "🔄 Processing room capacity data..."

# Run the capacity data processing script
python scripts/process-capacity-data.py

echo "✅ Capacity data processing complete"

echo "🚀 Deploying CDK stack..."

# Deploy the CDK stack
cdk deploy --require-approval never

echo "✅ Deployment complete!"

# Show the updated capacity data info
echo "📊 Capacity data summary:"
aws s3 ls s3://gatech-enrollment-dev-536580887192/capacity-data/ --human-readable

echo ""
echo "🎉 Georgia Tech Enrollment Backend deployed successfully!"
echo "API Endpoint: https://sjhiz24by9.execute-api.us-east-1.amazonaws.com/prod/api/v1/"