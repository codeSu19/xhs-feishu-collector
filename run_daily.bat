@echo off
:: 小红书笔记采集 - 每日自动运行脚本
cd /d D:\Project\xhs-feishu
python main.py >> logs\%date:~0,4%%date:~5,2%%date:~8,2%.log 2>&1
