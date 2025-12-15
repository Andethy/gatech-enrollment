#!/bin/bash

# One-command deployment script for Georgia Tech Enrollment Backend
# This script sets up and deploys the entire application from scratch

set -e

echo "🚀 Georgia Tech Enrollment Backend - One Command Deploy"
echo "======================================================"

# Check if we're in the right directory
if [ ! -f "README.md" ] || [ ! -d "infra" ] || [ ! -d "client" ]; then
    echo "❌ Error: Please run this script from the project root directory"
    exit 1
fi

# Check for required tools
echo "🔍 Checking prerequisites..."

# Check for Node.js
if ! command -v node &> /dev/null; then
    echo "❌ Node.js is required but not installed. Please install Node.js first."
    exit 1
fi

# Check for Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is required but not installed. Please install Python 3 first."
    exit 1
fi

# Check for AWS CLI
if ! command -v aws &> /dev/null; then
    echo "❌ AWS CLI is required but not installed. Please install AWS CLI first."
    exit 1
fi

# Check for CDK
if ! command -v cdk &> /dev/null; then
    echo "❌ AWS CDK is required but not installed. Installing CDK..."
    npm install -g aws-cdk
fi

echo "✅ Prerequisites check passed"

# Check for environment file
if [ ! -f "infra/.env" ]; then
    if [ -f "infra/.env.template" ]; then
        echo "⚠️  No .env file found. Please copy infra/.env.template to infra/.env and configure it."
        echo "   cp infra/.env.template infra/.env"
        echo "   Then edit infra/.env with your AWS configuration."
        exit 1
    else
        echo "❌ No environment configuration found. Please create infra/.env file."
        exit 1
    fi
fi

# Install infrastructure dependencies
echo "📦 Installing infrastructure dependencies..."
cd infra
npm install

# Install client dependencies
echo "📦 Installing client dependencies..."
cd ../client
npm install

# Build client
echo "🔨 Building client application..."
npm run build

# Return to infra directory for deployment
cd ../infra

# Process capacity data if script exists
if [ -f "scripts/process-capacity-data.py" ]; then
    echo "🔄 Processing room capacity data..."
    python3 scripts/process-capacity-data.py
    echo "✅ Capacity data processing complete"
fi

# Bootstrap CDK if needed (this is safe to run multiple times)
echo "🏗️  Bootstrapping CDK (if needed)..."
cdk bootstrap

# Deploy the stack
echo "🚀 Deploying CDK stack..."
cdk deploy --require-approval never

echo ""
echo "🎉 Deployment complete!"
echo ""
echo "📋 Next steps:"
echo "1. Update client/.env with the API Gateway URL from the CDK output"
echo "2. Deploy the client to your hosting platform"
echo ""
echo "💡 To redeploy after changes:"
echo "   ./deploy.sh"