#/bin/bash
curl http://localhost:8000/health
curl http://localhost:8001/health
curl http://localhost:8002/health

curl http://localhost:8000/metrics
curl http://localhost:8001/metrics
curl http://localhost:8002/metrics