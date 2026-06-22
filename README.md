# 📕 小红书笔记 → 飞书表格 采集分析工具

小红书复制链接 → 快捷指令发到群 → PC 脚本自动采集 + AI 分析。

---

## 整体架构

```
📱 手机                                    💻 电脑
───────                                   ───────
小红书 → 复制链接                           (一次性) python main.py --login-xhs
    ↓                                        ↓
快捷指令                                 Playwright 打开浏览器
    ↓                                        ↓
飞书群机器人 Webhook                     扫码登录小红书 → cookie 持久化
    ↓
群消息：笔记链接 + 标题                        ↓
    ↓                                   ───────────────────
                                         日常：python main.py
                                            ↓
                                         ① 采集群消息 → 写入表格
                                            ↓
                                         ② Playwright（已登录）抓全文
                                            ↓
                                         ③ DeepSeek AI 分析
                                            ↓
                                         ④ 回填表格 ✅
```

---

## 第一步：飞书侧配置

### 1.1 多维表格

字段结构：

| 字段名 | 类型 | 说明 |
|--------|------|------|
| 笔记链接 | URL 或 文本 | 小红书链接 |
| 完整文案 | 多行文本 | 笔记原文 |
| 笔记类型 | 单选 | 工具类/公式类/案例类/观点类/教程类/资讯类/数据类/选品类 |
| 领域标签 | 文本 | AI 填入 |
| 内容总结 | 多行文本 | AI 生成 |
| 核心要点 | 多行文本 | AI 生成 |
| 实用度 | 数字 | 1-5 |
| 处理状态 | 单选 | 待处理/已处理/分析失败 |
| 备注 | 多行文本 | 补充信息 |

Table ID 不需要手动找，`config.py` 留空即可自动发现。

### 1.2 群聊 + 机器人

```
1. 创建群聊 → 名称「笔记采集」
2. 群设置 → 群机器人 → 自定义机器人 → 名称随意
3. 复制 Webhook URL（快捷指令要用）
```

### 1.3 飞书应用权限

飞书开发者后台 → 应用「笔记采集」→ 权限管理：

| 权限 | 用途 |
|------|------|
| `bitable:app` | 读写多维表格 |
| `im:chat` 或 `im:chat:readonly` | 读取群聊列表 |
| `im:message.group_msg` | 读取群消息 |

---

## 第二步：iOS 快捷指令

> 📖 详细教程：[ios-shortcut-guide.md](ios-shortcut-guide.md)

快捷指令做的事：

```
获取剪贴板 → 提取纯 URL → 拼消息文本 → POST 到群机器人 Webhook
```

**手机操作：小红书 → 复制链接 → 点桌面图标 → 完成**

---

## 第三步：PC 配置

### 3.1 填写 `config.py`

```python
FEISHU_APP_ID = "cli_xxxxxxxx"
FEISHU_APP_SECRET = "xxxxxxxx"
BITABLE_APP_TOKEN = "xxxxxxxx"
AI_API_KEY = "sk-xxxxxxxx"       # DeepSeek Key

FETCH_METHOD = "playwright"      # 推荐：浏览器登录态抓取
```

### 3.2 安装依赖

```bash
pip install -r requirements.txt
playwright install chromium
```

### 3.3 一次性操作：登录小红书

```bash
python main.py --login-xhs
```

浏览器会自动打开 → 扫码或手机号登录 → 关掉浏览器。登录态保存在本地。

---

## 第四步：日常使用

```bash
python main.py
```

一步完成：采集群消息 → Playwright 抓全文 → AI 分析 → 回填表格。

---

## 命令速查

| 命令 | 作用 |
|------|------|
| `python main.py` | 采集 + 分析，一步到位 |
| `python main.py --login-xhs` | 浏览器登录小红书（仅首次） |
| `python main.py --list` | 列出多维表格中的所有表 |

---

## 成本

| 项目 | 费用 |
|------|------|
| 飞书 | 免费 |
| DeepSeek API | ¥1/百万 token → 月 < ¥1 |
| 服务器 | 无需，本地运行 |

---

## 常见问题

**Q: 抓取的内容不对？**
A: 先确认 `python main.py --login-xhs` 登录过小红书。登录态过期时重跑一次。

**Q: 飞书权限报错？**
A: 确认 bitable:app / im:chat / im:message.group_msg 三个权限都已开通并审批。

**Q: 想换 AI 模型？**
A: 改 `config.py`：`AI_PROVIDER = "openai"` / `"deepseek"` / `"anthropic"` / `"compatible"`
