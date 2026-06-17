#!/bin/bash
cd /home/qinbaisheng/agent/study_agent
source .venv/bin/activate
mkdir -p logs
nohup python3 agent.py > logs/agent.log 2>&1 &
