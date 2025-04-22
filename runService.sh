#!/bin/bash
cd /u01/middleware_api_24032025
source /u01/middleware_api_24032025/venv/bin/activate
pip install -r /u01/middleware_api_24032025/requirements.txt
#/u01/middleware_api_24032025/venv/bin/uvicorn app.api.main:app --reload --host 0.0.0.0 --port 8001
nohup /u01/middleware_api_24032025/venv/bin/uvicorn app.api.main:app --reload --host 0.0.0.0 --port 8001 > /u01/middleware_api_24032025/log.log 2>&1 &
