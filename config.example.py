"""
小红书笔记采集 - 配置文件模板
=======================
复制此文件为 config.py 并填写你的配置项。
"""

# ============================================================
# 1. 飞书应用配置
# ============================================================
# 在飞书开发者后台 (https://open.feishu.cn) 创建企业自建应用后获取
FEISHU_APP_ID = "cli_xxxxxxxxxxxx"
FEISHU_APP_SECRET = "xxxxxxxxxxxxxxxx"

# ============================================================
# 2. 飞书多维表格配置
# ============================================================
BITABLE_APP_TOKEN = "xxxxxxxx"      # 多维表格 URL 中 base/ 后面的部分
TABLE_ID = ""                       # 留空自动发现第一个表

# ============================================================
# 3. AI 模型配置
# ============================================================
# 支持: deepseek / openai / anthropic / compatible
AI_PROVIDER = "deepseek"
AI_MODEL = "deepseek-chat"
AI_API_KEY = "sk-xxxxxxxxxxxx"

# 仅当 AI_PROVIDER = "compatible" 时需要填写
AI_BASE_URL = "http://localhost:11434/v1"

# ============================================================
# 4. 字段名映射
# ============================================================
FIELD_LINK = "笔记链接"
FIELD_CONTENT = "完整文案"
FIELD_STATUS = "处理状态"
FIELD_NOTE_TYPE = "笔记类型"
FIELD_TAGS = "领域标签"
FIELD_SUMMARY = "内容总结"
FIELD_KEY_POINTS = "核心要点"
FIELD_USEFULNESS = "实用度"
FIELD_REMARK = "备注"

STATUS_PENDING = "待处理"
STATUS_DONE = "已处理"
STATUS_FAILED = "分析失败"

# ============================================================
# 5. 内容抓取配置
# ============================================================
FETCH_CONTENT = True                # 是否启用抓取
FETCH_METHOD = "playwright"         # playwright / jina / none
PLAYWRIGHT_USER_DATA = "./xhs_browser_profile"

# ============================================================
# 6. 快捷指令消息采集
# ============================================================
GROUP_CHAT_NAME = "笔记采集"         # 飞书群聊名称
