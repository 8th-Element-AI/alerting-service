#!/bin/bash

set -e

echo "🚀 Starting Error Monitoring System with Docker..."

# Build images
echo "📦 Building Docker images..."
docker-compose build

# Start services
echo "🐳 Starting services (PostgreSQL, Redis, MailHog, API)..."
docker-compose up -d postgres redis mailhog

# Wait for services to be ready
echo "⏳ Waiting for services to be healthy..."
sleep 10

# Initialize database
echo "🗄️  Initializing database..."
docker-compose run --rm api python init-db.py

# Start API server
echo "🌐 Starting API server..."
docker-compose up -d api

# Wait for API to be ready
echo "⏳ Waiting for API to be ready..."
sleep 5

# Run test client
echo "✅ Running test client..."
docker-compose run --rm test-client

echo ""
echo "=========================================="
echo "✨ Test completed!"
echo "=========================================="
echo ""
echo "📧 View email sent to MailHog:"
echo "   http://localhost:8025"
echo ""
echo "🛑 To stop all services, run:"
echo "   docker-compose down"
echo ""
