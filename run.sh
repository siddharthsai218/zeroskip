#!/usr/bin/env bash
set -e

echo "=========================================================="
echo "  Brightloop Software - ZeroSkip Subscription Engine"
echo "=========================================================="

# Check and install requirements if needed
if ! python -c "import fastapi, uvicorn, pydantic, bcrypt, jwt" 2>/dev/null; then
    echo "--> Installing dependencies from requirements.txt..."
    pip install -r requirements.txt
fi

# Seed demo data if database does not exist
if [ ! -f "zeroskip.db" ]; then
    echo "--> Initializing database and seeding Brightloop demo data..."
    python scripts/seed_demo.py
fi

echo ""
echo "🚀 Starting Brightloop Application Server..."
echo "  • Web Dashboard: http://localhost:8000"
echo "  • Swagger Docs:  http://localhost:8000/docs"
echo "  • Redoc Specs:   http://localhost:8000/redoc"
echo ""
echo "Press Ctrl+C to stop the server."
echo "=========================================================="

exec uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
