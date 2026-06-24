# 小红书笔记采集 - 创建 Windows 定时任务
# 以管理员身份运行此脚本

$taskName = "XHS-Feishu-Collector"
$scriptPath = "D:\Project\xhs-feishu\run_daily.bat"
$logDir = "D:\Project\xhs-feishu\logs"

# 创建日志目录
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

# 删除旧任务（如果存在）
Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue

# 创建新任务 — 每天上午 10:00 执行
$action = New-ScheduledTaskAction -Execute $scriptPath
$trigger = New-ScheduledTaskTrigger -Daily -At "10:00AM"
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries

Register-ScheduledTask -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Principal $principal `
    -Settings $settings `
    -Description "小红书笔记采集：每日自动采集群消息 + AI 分析 + 回填飞书表格"

Write-Host "✅ 定时任务已创建！"
Write-Host "   任务名: $taskName"
Write-Host "   执行时间: 每天上午 10:00"
Write-Host "   脚本路径: $scriptPath"
Write-Host ""
Write-Host "修改执行时间："
Write-Host "   1. 打开任务计划程序 (taskschd.msc)"
Write-Host "   2. 找到 XHS-Feishu-Collector"
Write-Host "   3. 触发器 → 编辑 → 修改时间"
Write-Host ""
Write-Host "手动测试运行："
Write-Host "   右键任务 → 运行"
