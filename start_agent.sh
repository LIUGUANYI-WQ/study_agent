#!/bin/bash
cd /home/$(whoami)/study_agent
# 激活虚拟环境并后台运行程序
source .venv/bin/activate
nohup python3 agent.py > logs/agent.log 2>&1 &
