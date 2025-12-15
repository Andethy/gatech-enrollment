#!/bin/bash

# Setup script for new developers
# This script prepares the development environment

set -e

echo "🛠️  Georgia Tech Enrollment Backend - Development Setup"
echo "====================================================="

# Check if we're in the right directory
if [ ! -f "README.md" ] || [ ! -d "infra" ] || [ ! -d "client" ]; then
    echo "❌ Error: Please run this script from the project root directory"
    exit 1
fi

# Copy environment templates
echo "📋 Setting up environment files..."

if [ ! -f "infra/.env" ]; then
    if [ -f "infra/.env.template" ]; then
        cp infra/.env.template infra/.env
        echo "✅ Created infra/.env from template"
        echo "⚠️  Please edit infra/.env with your AWS configuration"
    else
        echo "❌ infra/.env.template not found"
        exit 1
    fi
else
    echo "ℹ️  infra/.env already exists"
fi

if [ ! -f "client/.env" ]; then
    if [ -f "client/.env.template" ]; then
        cp client/.env.template client/.env
        echo "✅ Created client/.env from template"
        echo "⚠️  Please edit client/.env with your API URL after deployment"
    else
        echo "❌ client/.env.template not found"
        exit 1
    fi
else
    echo "ℹ️  client/.env already exists"
fi

# Install dependencies
echo "📦 Installing dependencies..."

echo "  Installing infrastructure dependencies..."
cd infra
npm install

echo "  Installing client dependencies..."
cd ../client
npm install

cd ..

echo ""
echo "✅ Setup complete!"
echo ""
echo "📋 Next steps:"
echo "1. Edit infra/.env with your AWS configuration"
echo "2. Run './deploy.sh' to deploy the backend"
echo "3. Update client/.env with the API URL from deployment output"
echo "4. Run 'cd client && npm run dev' for local development"