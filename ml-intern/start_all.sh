#!/bin/bash

# Cleanup function to kill all background processes when you press Ctrl+C
cleanup() {
    echo ""
    echo "🛑 Shutting down all services..."
    kill $(jobs -p) 2>/dev/null
    exit 0
}
trap cleanup INT TERM EXIT

echo "🚀 Starting Complete ML Intern Stack..."
echo "================================================="

# 1. Start OmniRoute
echo "🟢 [1/4] Starting OmniRoute (Dashboard: http://localhost:20128)"
cd /Users/mathewbijugeorge/Downloads/OmniRoute
export RATE_LIMIT_MAX_WAIT_MS=300000
> /tmp/omniroute.log # Clear the old log file for fresh reporting
(while true; do npm run dev 2>&1 | tee -a /tmp/omniroute.log > /dev/null; sleep 2; done) &

# 2. Start Backend
echo "🟢 [2/4] Starting Backend (API: http://localhost:7860)"
cd /Users/mathewbijugeorge/Downloads/ml-intern-main/backend
source $HOME/.local/bin/env
uv run uvicorn main:app --host ::1 --port 7860 --env-file ../.env > /dev/null 2>&1 &

# 3. Start Frontend
echo "🟢 [3/4] Starting Frontend (UI: http://localhost:5173)"
cd /Users/mathewbijugeorge/Downloads/ml-intern-main/frontend
npm run dev > /dev/null 2>&1 &

echo "⏳ Waiting a few seconds for services to boot..."
sleep 4

# 4. Start Locust
echo "🟢 [4/4] Starting Locust Load Test (UI: http://localhost:8089)"
cd /Users/mathewbijugeorge/Downloads/ml-intern-main/load_tests
uv run locust -f locustfile.py --host=http://localhost:5173

# Keep the script alive if Locust exits
wait
