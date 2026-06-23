"""
小红书笔记采集 - 主程序
=====================
功能：读取飞书多维表格中「待处理」的笔记，调用 AI 分析，
      将分析结果（笔记类型、内容总结、核心要点等）回填到表格中。

用法：python main.py
"""

import json
import re
import sys
import time
from datetime import datetime

# Windows 终端编码修复（避免 emoji 显示乱码）
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import requests
import lark_oapi as lark
from lark_oapi.api.bitable.v1 import *

from config import (
    FEISHU_APP_ID,
    FEISHU_APP_SECRET,
    BITABLE_APP_TOKEN,
    TABLE_ID,
    AI_PROVIDER,
    AI_MODEL,
    AI_API_KEY,
    AI_BASE_URL,
    FIELD_LINK,
    FIELD_CONTENT,
    FIELD_STATUS,
    FIELD_NOTE_TYPE,
    FIELD_TAGS,
    FIELD_SUMMARY,
    FIELD_KEY_POINTS,
    FIELD_USEFULNESS,
    FIELD_REMARK,
    STATUS_PENDING,
    STATUS_DONE,
    STATUS_FAILED,
    FETCH_CONTENT,
    GROUP_CHAT_NAME,
    FETCH_METHOD,
    PLAYWRIGHT_USER_DATA,
)


# ============================================================
# 初始化客户端
# ============================================================

feishu_client = lark.Client.builder() \
    .app_id(FEISHU_APP_ID) \
    .app_secret(FEISHU_APP_SECRET) \
    .build()


def _init_ai_client():
    """
    根据 AI_PROVIDER 配置初始化对应的 AI 客户端。
    返回 (client, call_fn) —— client 是 SDK 实例，call_fn 是统一的调用函数。
    """
    if AI_PROVIDER in ("deepseek", "openai", "compatible"):
        from openai import OpenAI

        if AI_PROVIDER == "deepseek":
            base_url = "https://api.deepseek.com"
        elif AI_PROVIDER == "openai":
            base_url = None  # 使用默认地址
        else:  # compatible
            base_url = AI_BASE_URL

        client = OpenAI(api_key=AI_API_KEY, base_url=base_url)

        def call_openai(prompt_text: str) -> str:
            response = client.chat.completions.create(
                model=AI_MODEL,
                temperature=0.3,
                max_tokens=1024,
                messages=[
                    {"role": "system", "content": "你是一个专业的电商内容分析助手。永远只返回 JSON，不返回其他内容。"},
                    {"role": "user", "content": prompt_text},
                ],
            )
            return response.choices[0].message.content

        return client, call_openai

    elif AI_PROVIDER == "anthropic":
        from anthropic import Anthropic

        client = Anthropic(api_key=AI_API_KEY)

        def call_anthropic(prompt_text: str) -> str:
            response = client.messages.create(
                model=AI_MODEL,
                max_tokens=1024,
                temperature=0.3,
                system="你是一个专业的电商内容分析助手。永远只返回 JSON，不返回其他内容。",
                messages=[{"role": "user", "content": prompt_text}],
            )
            return response.content[0].text

        return client, call_anthropic

    else:
        raise ValueError(f"不支持的 AI_PROVIDER: {AI_PROVIDER}，可选: deepseek / openai / anthropic / compatible")


ai_client = None
ai_call = None

def _get_ai_client():
    """延迟初始化 AI 客户端（只有分析时才需要）。"""
    global ai_client, ai_call
    if ai_call is None:
        ai_client, ai_call = _init_ai_client()
    return ai_client, ai_call


# ============================================================
# 飞书表格操作
# ============================================================

def list_tables():
    """
    列出多维表格中所有的数据表。
    """
    print(f"\n📋 正在查询 app_token={BITABLE_APP_TOKEN} 下的所有表...\n")

    request = ListAppTableRequest.builder() \
        .app_token(BITABLE_APP_TOKEN) \
        .build()

    response = feishu_client.bitable.v1.app_table.list(request)

    if not response.success():
        print(f"❌ 查询失败: {response.msg}")
        print(f"   请检查: ① BITABLE_APP_TOKEN 是否正确  ② 应用是否已开通 bitable:app 权限")
        return []

    tables = response.data.items
    if not tables:
        print("⚠️ 该多维表格下没有任何数据表")
        return []

    print(f"{'序号':<6} {'表名':<30} {'table_id'}")
    print("-" * 80)
    for i, t in enumerate(tables, 1):
        print(f"{i:<6} {t.name:<30} {t.table_id}")
    print()

    return tables


def auto_detect_table_id():
    """
    自动获取第一个数据表的 table_id。
    如果 config.py 中 TABLE_ID 为空则调用此函数。
    """
    tables = list_tables()
    if tables:
        table_id = tables[0].table_id
        print(f"✅ 自动选择第一个表: [{tables[0].name}] → {table_id}")
        return table_id
    return None


def get_table_id():
    """
    获取有效的 table_id：优先用 config 中的值，为空则自动检测。
    结果会缓存，不会重复打印表列表。
    """
    if TABLE_ID and TABLE_ID != "tblxxxxxxxx":
        return TABLE_ID

    # 缓存：只检测一次
    if not hasattr(get_table_id, "_cached"):
        tid = auto_detect_table_id()
        get_table_id._cached = tid

    return get_table_id._cached


def get_pending_records():
    """
    获取飞书表格中所有「待处理」的行。
    返回 list[dict]，每个 dict 包含 record_id 和 fields。
    """
    table_id = get_table_id()
    if not table_id:
        print("❌ 无法获取 table_id，请检查 BITABLE_APP_TOKEN 配置，或手动指定 TABLE_ID")
        return []

    all_records = []
    page_token = None

    while True:
        builder = ListAppTableRecordRequest.builder() \
            .app_token(BITABLE_APP_TOKEN) \
            .table_id(table_id) \
            .page_size(50)
        if page_token:
            builder = builder.page_token(page_token)
        request = builder.build()

        response = feishu_client.bitable.v1.app_table_record.list(request)

        if not response.success():
            print(f"❌ 读取飞书表格失败: {response.msg}")
            return []

        if response.data.items:
            for item in response.data.items:
                fields = item.fields
                # 客户端过滤：只保留状态为「待处理」的记录
                status = fields.get(FIELD_STATUS, "")
                if status == STATUS_PENDING:
                    all_records.append({
                        "record_id": item.record_id,
                        "fields": fields,
                    })

        if response.data.has_more and response.data.page_token:
            page_token = response.data.page_token
        else:
            break

    return all_records


def update_record(record_id: str, fields: dict):
    """
    更新飞书表格中的一行数据。
    """
    table_id = get_table_id()
    if not table_id:
        return False

    request = UpdateAppTableRecordRequest.builder() \
        .app_token(BITABLE_APP_TOKEN) \
        .table_id(table_id) \
        .record_id(record_id) \
        .request_body(AppTableRecord.builder().fields(fields).build()) \
        .build()

    response = feishu_client.bitable.v1.app_table_record.update(request)

    if not response.success():
        print(f"  ⚠️ 更新失败: {response.msg}")
        return False
    return True


def create_record(fields: dict) -> bool:
    """
    在飞书表格中新增一行记录。
    自动处理 URL 字段格式：传入纯字符串，内部转为 {link: url}。
    """
    table_id = get_table_id()
    if not table_id:
        return False

    # 如果笔记链接字段是 URL 类型，需要 {"link": "..."} 格式
    link_val = fields.get(FIELD_LINK, "")
    if isinstance(link_val, str) and link_val:
        fields = {**fields, FIELD_LINK: {"link": link_val}}

    request = CreateAppTableRecordRequest.builder() \
        .app_token(BITABLE_APP_TOKEN) \
        .table_id(table_id) \
        .request_body(AppTableRecord.builder().fields(fields).build()) \
        .build()

    response = feishu_client.bitable.v1.app_table_record.create(request)

    if not response.success():
        print(f"  ⚠️ 创建记录失败: {response.msg} (code={response.code})")
        return False
    return True


def extract_url(value):
    """
    从飞书字段值中提取纯 URL 字符串。
    支持两种格式：纯字符串 "https://..." 或对象 {"link": "https://..."}
    """
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        return value.get("link", "").strip()
    return ""


def get_existing_urls() -> set:
    """
    获取表格中已有的笔记链接（用于去重）。
    """
    table_id = get_table_id()
    if not table_id:
        return set()

    urls = set()
    page_token = None

    while True:
        builder = ListAppTableRecordRequest.builder() \
            .app_token(BITABLE_APP_TOKEN) \
            .table_id(table_id) \
            .page_size(500)
        if page_token:
            builder = builder.page_token(page_token)
        request = builder.build()

        response = feishu_client.bitable.v1.app_table_record.list(request)

        if not response.success():
            break

        if response.data.items:
            for item in response.data.items:
                link = extract_url(item.fields.get(FIELD_LINK, ""))
                if link:
                    urls.add(link)

        if response.data.has_more and response.data.page_token:
            page_token = response.data.page_token
        else:
            break

    return urls


# ============================================================
# 消息采集
# ============================================================

def get_tenant_token() -> str:
    """获取飞书 tenant_access_token。"""
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    body = {"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET}
    resp = requests.post(url, json=body, timeout=15)
    data = resp.json()
    if data.get("code") != 0:
        raise Exception(f"获取 token 失败: {data}")
    return data["tenant_access_token"]


def find_chat_id(token: str, group_name: str) -> str | None:
    """查找群聊 ID。"""
    url = "https://open.feishu.cn/open-apis/im/v1/chats"
    headers = {"Authorization": f"Bearer {token}"}
    params = {"page_size": 100}

    while True:
        resp = requests.get(url, headers=headers, params=params, timeout=15)
        data = resp.json()
        if data.get("code") != 0:
            print(f"  列出群聊失败: {data}")
            return None
        for item in data.get("data", {}).get("items", []):
            if item.get("name") == group_name:
                return item["chat_id"]
        if not data.get("data", {}).get("has_more"):
            break
        params["page_token"] = data["data"]["page_token"]

    return None


def list_recent_messages(token: str, chat_id: str, limit: int = 50) -> list:
    """获取群聊最近的消息。"""
    url = "https://open.feishu.cn/open-apis/im/v1/messages"
    headers = {"Authorization": f"Bearer {token}"}
    params = {
        "container_id_type": "chat",
        "container_id": chat_id,
        "page_size": min(limit, 50),
        "sort_type": "ByCreateTimeDesc",
    }

    messages = []
    resp = requests.get(url, headers=headers, params=params, timeout=15)
    data = resp.json()
    if data.get("code") != 0:
        print(f"  获取消息失败: {data}")
        return messages

    for item in data.get("data", {}).get("items", []):
        msg_type = item.get("msg_type", "")
        content_str = item.get("body", {}).get("content", "{}")
        try:
            content = json.loads(content_str)
            text = content.get("text", "")
        except json.JSONDecodeError:
            text = ""

        if text:
            messages.append({
                "message_id": item.get("message_id"),
                "text": text,
                "create_time": item.get("create_time", ""),
            })

    return messages


def parse_note_message(text: str) -> dict | None:
    """
    从消息文本中解析笔记链接和内容。
    支持的格式：
      笔记链接
      https://xhslink.com/xxx
      笔记内容
      文案正文...
    或者简单格式：
      https://xhslink.com/xxx
      文案正文...
    """
    link = None
    content = ""

    # 尝试 "笔记链接" 标签格式
    link_match = re.search(r'笔记链接\s*\n\s*(https?://\S+)', text)
    if link_match:
        link = link_match.group(1).strip()
    else:
        # 尝试直接找 URL
        url_match = re.search(r'(https?://xhslink\.com/\S+)', text)
        if url_match:
            link = url_match.group(1).strip()

    # 提取内容
    content_match = re.search(r'笔记内容\s*\n(.+)', text, re.DOTALL)
    if content_match:
        content = content_match.group(1).strip()
    else:
        # 去掉链接行，剩余作为内容
        if link:
            content = re.sub(r'https?://\S+', '', text).strip()
            content = re.sub(r'笔记链接\s*', '', content).strip()

    if not link:
        return None

    # 群消息里的标题写入表格作为兜底。
    # process_all() 会优先从链接抓全文，抓失败才用这个。
    return {
        "笔记链接": link,
        "完整文案": content[:5000] if content else "",
        "处理状态": STATUS_PENDING,
    }


def collect_messages():
    """
    从飞书群聊读取消息，解析笔记数据写入表格。
    """
    print("=" * 60)
    print(f"📬 消息采集模式")
    print(f"   目标群聊: {GROUP_CHAT_NAME}")
    print(f"   启动时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # 1. 获取 token
    print("\n[1] 获取 tenant_access_token...")
    try:
        token = get_tenant_token()
        print(f"   ✅ Token: {token[:25]}...")
    except Exception as e:
        print(f"   ❌ {e}")
        return

    # 2. 查找群聊
    print(f"\n[2] 查找群聊「{GROUP_CHAT_NAME}」...")
    chat_id = find_chat_id(token, GROUP_CHAT_NAME)
    if not chat_id:
        print(f"   ❌ 未找到群聊「{GROUP_CHAT_NAME}」")
        print(f"   请确认: ① 群已创建  ② 应用已添加到群  ③ 群名完全一致")
        return
    print(f"   ✅ Chat ID: {chat_id}")

    # 3. 获取最近消息
    print(f"\n[3] 获取最近消息...")
    messages = list_recent_messages(token, chat_id, limit=50)
    print(f"   获取到 {len(messages)} 条消息")

    if not messages:
        print("\n✅ 没有消息需要处理。")
        return

    # 4. 获取已有链接（去重）
    print(f"\n[4] 获取表格中已有链接...")
    existing_urls = get_existing_urls()
    print(f"   已有 {len(existing_urls)} 条记录")

    # 5. 解析并写入
    print(f"\n[5] 解析消息并写入表格...\n")
    new_count = 0
    skip_count = 0

    for msg in messages:
        parsed = parse_note_message(msg["text"])
        if not parsed:
            continue

        url = parsed["笔记链接"]
        if url in existing_urls:
            skip_count += 1
            continue

        if create_record(parsed):
            link_short = url[:60]
            content_len = len(parsed.get("完整文案", ""))
            print(f"  ✅ {link_short}... (文案 {content_len} 字)")
            existing_urls.add(url)
            new_count += 1
        else:
            print(f"  ❌ 写入失败: {url[:60]}...")

    print()
    print("=" * 60)
    print(f"📊 采集完成！")
    print(f"   新增: {new_count} 条")
    print(f"   跳过(重复): {skip_count} 条")
    print(f"   扫描消息: {len(messages)} 条")
    print(f"   接下来将由 AI 逐条分析...")
    print("=" * 60)

# 手机端 User-Agent（降低被反爬的概率）
MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Version/17.0 Mobile/15E148 Safari/604.1"
)


def clean_jina_content(raw: str) -> str:
    """
    清洗 Jina Reader 返回的杂乱内容，只保留笔记标题和正文。
    去掉登录、导航、备案号、图片链接、footer 等不相干的文案。
    """
    lines = raw.split("\n")
    result = []
    boilerplate_found = False

    # 匹配垃圾行的关键词/正则
    trash_patterns = [
        r"登录",
        r"验证码",
        r"扫码",
        r"\+86",
        r"手机号",
        r"获取验证",
        r"我已阅读",
        r"用户协议",
        r"隐私政策",
        r"个人信息保护",
        r"同意并继续",
        r"取消$",
        r"^创作中心$",
        r"^业务合作$",
        r"^发现$",
        r"^RED$",
        r"^直播$",
        r"^发布$",
        r"^通知$",
        r"^关注$",
        r"^LIVE$",
        r"沪ICP备",
        r"营业执照",
        r"沪公网安备",
        r"增值电信",
        r"医疗器械",
        r"互联网药品",
        r"举报电话",
        r"举报中心",
        r"网上有害",
        r"自营经营者",
        r"网络文化经营许可",
        r"个性化推荐算法",
        r"网信算备",
        r"行吟信息科技",
        r"上海市黄浦区",
        r"电话：9501",
        r"关于我们",
        r"^更多$",
        r"^© 2014",
        r"^\\(c\\) 2014",
        r"^\\© 2014",
        r"可用$",
        r"微信$",
        r"阅读并同意",
        r"新用户可直接登录",
        r"URL Source:",
        r"Markdown Content:",
        # 新增小红书 UI 文字
        r"小红书 - 你的生活兴趣社区",
        r"你的生活兴趣社区",
        r"帮助与反馈",
        r"帮助与客服",
        r"生活兴趣社区",
        r"^\s*小红书\s*$",
        r"^\s*或\s*$",
        r"小红书 App 点击",
        r"^小红书$",
    ]

    for line in lines:
        stripped = line.strip()

        # 跳过空行
        if not stripped:
            if result and result[-1] != "":
                result.append("")
            continue

        # 跳过纯图片引用
        if re.match(r"^!\[.*\]\(.*\)$", stripped):
            continue

        # 跳过纯链接行
        if re.match(r"^https?://\S+$", stripped):
            continue

        # 跳过 blob 链接
        if "blob:http" in stripped:
            continue

        # 跳过 Title: / URL Source: / Markdown Content: 元信息行
        if re.match(r"^(Title|URL Source|Markdown Content):", stripped):
            # 只保留 Title 后面的标题文字
            title_match = re.match(r"^Title:\s*(.+?)(?:\s*-\s*小红书)?$", stripped)
            if title_match:
                title = title_match.group(1).strip()
                if title and len(title) > 2:
                    result.append(title)
            continue

        # 检查是否匹配垃圾模式
        is_trash = False
        for pat in trash_patterns:
            if re.search(pat, stripped):
                is_trash = True
                break

        if is_trash:
            continue

        # 跳过只包含特殊字符的行
        if len(stripped) < 3 and not re.search(r"[一-鿿]", stripped):
            continue

        # 检查是否为 boilerplate 页脚（连续垃圾行之后的全跳过）
        result.append(stripped)

    # 合并去重空行
    cleaned = "\n".join(result).strip()
    # 把连续 3 个以上空行压成 2 个
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)

    # 质量检查：清洗后全是 UI 文字而非笔记内容
    if len(cleaned) < 80:
        return cleaned  # 太短，上层会判断丢弃

    # 检查是否全是短行（说明是导航/列表，不是笔记正文）
    content_lines = [l for l in cleaned.split("\n") if l.strip()]
    if content_lines:
        avg_len = sum(len(l) for l in content_lines) / len(content_lines)
        if avg_len < 15:
            return ""  # 全是导航短句，丢弃

    return cleaned


def fetch_with_playwright(url: str) -> str | None:
    """
    用 Playwright + 持久化登录态抓取小红书笔记内容。
    需要先运行 python main.py --login-xhs 登录一次。
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("    未安装 playwright，请运行: pip install playwright && playwright install chromium")
        return None

    import os as _os
    _os.makedirs(PLAYWRIGHT_USER_DATA, exist_ok=True)

    try:
        with sync_playwright() as p:
            # 用持久化 context，保存登录态
            context = p.chromium.launch_persistent_context(
                user_data_dir=PLAYWRIGHT_USER_DATA,
                headless=True,
                args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
                user_agent=MOBILE_UA,
                viewport={"width": 390, "height": 844},
                locale="zh-CN",
            )
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=30000)

            # 等待内容加载
            try:
                page.wait_for_selector("#detail-desc, .note-text, .note-scroller, [class*='note']", timeout=10000)
            except Exception:
                pass
            page.wait_for_timeout(2000)  # 额外等待动态渲染

            # 提取标题
            title = ""
            title_selectors = ["#detail-title", ".note-title", "h1", "[class*='title']"]
            for sel in title_selectors:
                try:
                    el = page.query_selector(sel)
                    if el:
                        title = el.inner_text().strip()
                        if len(title) > 2:
                            break
                except Exception:
                    continue

            # 提取正文
            body = ""
            body_selectors = ["#detail-desc", ".note-text", ".note-scroller", "[class*='desc']", "[class*='content']"]
            for sel in body_selectors:
                try:
                    el = page.query_selector(sel)
                    if el:
                        body = el.inner_text().strip()
                        if len(body) > 50:
                            break
                except Exception:
                    continue

            # 如果上述选择器都失败，取整个页面可见文本
            if not body or len(body) < 50:
                try:
                    full_text = page.inner_text("body")
                    # 清洗 — 复用 clean_jina_content
                    body = clean_jina_content(full_text)
                except Exception:
                    pass

            context.close()

            # 质量检查：内容必须有足够中文字符（排除登录墙、空白页）
            def quality_ok(text):
                cn_chars = len(re.findall(r'[一-鿿]', text))
                return cn_chars >= 30

            if title and body:
                result = f"{title}\n\n{body}"
                if quality_ok(result):
                    return result[:5000]
                else:
                    print(f"    内容质量不达标（中文{len(re.findall(r'[一-鿿]', result))}字），丢弃")
            elif body and len(body) > 80:
                if quality_ok(body):
                    return body[:5000]
                else:
                    print(f"    内容质量不达标，丢弃")
            elif title:
                return f"[仅标题] {title}"
            return None

    except Exception as e:
        print(f"    Playwright 抓取失败: {e}")
        return None


def login_xiaohongshu():
    """打开浏览器让用户手动登录小红书，登录态保存到 PLAYWRIGHT_USER_DATA。"""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("请先运行: pip install playwright && playwright install chromium")
        return

    import os as _os
    _os.makedirs(PLAYWRIGHT_USER_DATA, exist_ok=True)

    print("=" * 60)
    print("正在打开浏览器，请在浏览器中登录小红书...")
    print("登录成功后关闭浏览器窗口即可。")
    print("=" * 60)

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=PLAYWRIGHT_USER_DATA,
            headless=False,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
            viewport={"width": 390, "height": 844},
            locale="zh-CN",
        )
        page = context.new_page()
        page.goto("https://www.xiaohongshu.com", wait_until="domcontentloaded", timeout=30000)

        print("\n请扫码或手机号登录小红书。")
        print("登录完成后，关闭浏览器窗口，或按 Ctrl+C 退出。\n")

        try:
            # 等待用户手动关闭浏览器
            page.wait_for_timeout(600000)  # 最多等 10 分钟
        except KeyboardInterrupt:
            pass

        context.close()
        print("登录态已保存到:", PLAYWRIGHT_USER_DATA)


def fetch_note_content(url: str) -> str | None:
    """
    尝试从小红书链接抓取笔记全文。
    按 FETCH_METHOD 配置选择抓取方式。
    """
    if not FETCH_CONTENT or FETCH_METHOD == "none":
        return None

    url = str(url).strip()

    # 短链预处理：xhslink.com → xiaohongshu.com 真实地址
    if "xhslink.com" in url:
        try:
            print(f"    解析短链...")
            resp = requests.head(url, allow_redirects=True, timeout=10,
                                 headers={"User-Agent": MOBILE_UA})
            real_url = resp.url
            if real_url != url and "xiaohongshu.com" in real_url:
                print(f"    重定向 → {real_url[:80]}...")
                url = real_url
        except Exception:
            pass  # 解析失败就用原链接

    # 方式 1：Playwright（已登录浏览器）
    if FETCH_METHOD == "playwright":
        print(f"    尝试 Playwright（已登录）...")
        result = fetch_with_playwright(url)
        if result and len(result) > 80:
            return result
        if result:
            print(f"    Playwright 结果太短({len(result)}字)")

    # 方式 2：Jina Reader
    if FETCH_METHOD in ("jina", "playwright"):
        print(f"    尝试 Jina Reader...")
        try:
            resp = requests.get(
                f"https://r.jina.ai/{url}",
                headers={"User-Agent": MOBILE_UA, "Accept": "text/markdown"},
                timeout=20,
            )
            if resp.status_code == 200 and resp.text and len(resp.text.strip()) > 100:
                raw = resp.text.strip()
                cleaned = clean_jina_content(raw)
                if len(cleaned) > 50:
                    return cleaned[:5000]
                print(f"    清洗后内容太短({len(cleaned)}字)")
        except Exception as e:
            print(f"    Jina Reader 失败: {e}")

    # 方式 3：直接请求
    if FETCH_METHOD in ("jina",):
        try:
            print(f"    尝试直接请求...")
            resp = requests.get(url, headers={"User-Agent": MOBILE_UA}, timeout=15, allow_redirects=True)
            if resp.status_code == 200 and resp.text:
                desc_match = re.search(
                    r'<meta[^>]+name="description"[^>]+content="([^"]+)"',
                    resp.text, re.IGNORECASE,
                )
                if desc_match and len(desc_match.group(1)) > 30:
                    return desc_match.group(1)[:5000]
                title_match = re.search(
                    r'<meta[^>]+property="og:title"[^>]+content="([^"]+)"',
                    resp.text, re.IGNORECASE,
                )
                if title_match:
                    return f"[仅标题] {title_match.group(1)}"
        except Exception as e:
            print(f"    直接请求失败: {e}")

    return None


# ============================================================
# AI 分析
# ============================================================

# 笔记分析 Prompt 模板
ANALYSIS_PROMPT = """你是一个专业的电商社媒内容分析助手。请分析以下小红书笔记，返回结构化的分析结果。

## 笔记内容
{content}

{link_line}

## 分析要求

1. **笔记类型**: 从以下分类中选择最匹配的 1 个：
   - 工具类：推荐或评测电商工具、插件、软件、SaaS
   - 公式类：分享运营公式、定价公式、ROI计算、数据指标
   - 案例类：分享具体店铺/品牌的运营案例、成功/失败复盘
   - 观点类：发表对电商行业的看法、趋势判断、个人见解
   - 教程类：步骤式的操作教学、手把手教程
   - 资讯类：行业新闻、政策变化、平台规则更新
   - 数据类：分享数据报告、行业统计、调研数据
   - 选品类：推荐或分析热销品类、蓝海品类、选品思路

2. **领域标签**: 从以下选择 1-3 个相关标签：
   跨境电商、国内电商、直播带货、短视频、独立站、供应链、营销投放、数据分析、私域运营、AI应用

3. **内容总结**: 80-150字概括笔记核心内容，突出对电商从业者的价值

4. **核心要点**: 提取 3-5 个关键信息点，每条不超过 40 字

5. **实用度评分**: 1-5 分（5=非常有价值，1=价值较低）

## 输出格式
请严格按照以下 JSON 格式返回，不要包含其他文字：
```json
{{
  "note_type": "工具类",
  "tags": ["标签1", "标签2"],
  "summary": "内容总结文字...",
  "key_points": ["要点1", "要点2", "要点3"],
  "usefulness": 4
}}
```"""


def analyze_note(link: str, content: str) -> dict | None:
    """
    调用 AI 分析笔记内容。
    返回解析后的 dict，失败返回 None。
    """
    link_line = f"**笔记链接**: {link}" if link else ""

    prompt = ANALYSIS_PROMPT.format(
        content=str(content)[:5000],  # 截断过长内容，控制 token 消耗
        link_line=link_line,
    )

    try:
        _, call_fn = _get_ai_client()
        text = call_fn(prompt)
        if text is None:
            print("  ⚠️ AI 返回为空")
            return None

        # 提取 JSON（可能在 ```json ... ``` 代码块中，也可能直接是 JSON）
        json_match = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            # 尝试直接找 JSON 对象
            json_match = re.search(r'\{.*\}', text, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
            else:
                json_str = text

        result = json.loads(json_str)
        return result

    except json.JSONDecodeError as e:
        print(f"  ⚠️ JSON 解析失败: {e}")
        print(f"  原始返回: {text[:500] if text else '(空)'}")
        return None
    except Exception as e:
        print(f"  ⚠️ AI 调用失败: {e}")
        return None


# ============================================================
# 主处理流程
# ============================================================

def process_all():
    """
    主流程：采集群消息 → AI 分析 → 回填结果。一步到位。
    """
    # ---- Step 0: 先从群聊采集消息到表格 ----
    collect_messages()

    print()
    print("=" * 60)
    print(f"📊 小红书笔记采集分析工具")
    print(f"   AI 引擎: {AI_PROVIDER} / {AI_MODEL}")
    print(f"   内容抓取: {'开启' if FETCH_CONTENT else '关闭'}（填 false 可跳过）")
    print(f"   启动时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # 1. 获取待处理记录
    records = get_pending_records()
    if not records:
        print("\n✅ 没有待处理的笔记，表格已是最新状态。")
        return

    print(f"\n📋 发现 {len(records)} 条待处理笔记，开始分析...\n")
    success_count = 0
    fail_count = 0

    # 2. 逐条处理
    for i, record in enumerate(records, 1):
        record_id = record["record_id"]
        fields = record["fields"]
        link = extract_url(fields.get(FIELD_LINK, ""))
        content = fields.get(FIELD_CONTENT, "")

        # 从链接中提取一个简短标识用于日志
        link_short = str(link)[:60] if link else "(无链接)"
        print(f"[{i}/{len(records)}] {link_short}...")

        # 优先从链接抓取全文（VPN 环境下成功），抓不到用群消息兜底
        existing_content = str(content).strip() if content else ""
        if FETCH_CONTENT and link:
            print(f"  📡 尝试从链接抓取全文...")
            fetched = fetch_note_content(str(link))
            if fetched:
                content = fetched
                update_record(record_id, {FIELD_CONTENT: content})
                print(f"  ✅ 抓取成功 ({len(content)} 字)")
            elif existing_content:
                print(f"  ⚠️ 抓取失败，用群消息标题兜底 ({len(existing_content)} 字)")
                content = existing_content
            else:
                print(f"  ⚠️ 抓取失败且无兜底，需手动补充")
                update_record(record_id, {FIELD_STATUS: STATUS_FAILED, FIELD_REMARK: "抓取失败，请在表格中手动粘贴原文后重跑"})
                fail_count += 1
                continue
        elif not existing_content:
            print(f"  ⚠️ 无内容可分析，跳过")
            update_record(record_id, {FIELD_STATUS: STATUS_FAILED, FIELD_REMARK: "文案为空，关闭了抓取"})
            fail_count += 1
            continue
        else:
            content = existing_content

        # 调用 AI 分析
        analysis = analyze_note(str(link), str(content))

        if analysis is None:
            update_record(record_id, {FIELD_STATUS: STATUS_FAILED, FIELD_REMARK: "AI分析失败"})
            fail_count += 1
            continue

        # 组装更新字段
        key_points_text = "\n".join(f"• {p}" for p in analysis.get("key_points", []))
        tags_text = ", ".join(analysis.get("tags", []))
        remark_text = f"实用度: {analysis.get('usefulness', '-')}/5 | 引擎: {AI_PROVIDER}"

        update_fields = {
            FIELD_NOTE_TYPE: analysis.get("note_type", ""),
            FIELD_TAGS: tags_text,
            FIELD_SUMMARY: analysis.get("summary", ""),
            FIELD_KEY_POINTS: key_points_text,
            FIELD_USEFULNESS: analysis.get("usefulness", 0),
            FIELD_STATUS: STATUS_DONE,
            FIELD_REMARK: remark_text,
        }

        if update_record(record_id, update_fields):
            print(f"  ✅ 完成 [{analysis.get('note_type', 'N/A')}] {analysis.get('summary', '')[:50]}...")
            success_count += 1
        else:
            fail_count += 1

        # 避免请求过快
        if i < len(records):
            time.sleep(1)

    # 3. 输出汇总
    print()
    print("=" * 60)
    print(f"📊 处理完成！")
    print(f"   成功: {success_count} 条")
    print(f"   失败: {fail_count} 条")
    print(f"   总计: {len(records)} 条")
    print("=" * 60)


# ============================================================
# 自检
# ============================================================

def check_all():
    """一键自检所有连接：飞书 / AI / Playwright。"""
    print("=" * 60)
    print("🔍 系统自检")
    print("=" * 60)

    results = []

    # 1. 飞书 Token
    print("\n[1] 飞书 Token ...", end=" ")
    try:
        token = get_tenant_token()
        print(f"✅ {token[:20]}...")
        results.append(("飞书 Token", True, ""))
    except Exception as e:
        print(f"❌ {e}")
        results.append(("飞书 Token", False, str(e)))

    # 2. 多维表格
    print("[2] 多维表格 ...", end=" ")
    try:
        tables = list_tables()
        if tables:
            tid = get_table_id()
            print(f"✅ {tables[0].name} ({tid})")
            results.append(("多维表格", True, tid))
        else:
            print("⚠️  无数据表")
            results.append(("多维表格", False, "无数据表"))
    except Exception as e:
        print(f"❌ {e}")
        results.append(("多维表格", False, str(e)))

    # 3. 群聊
    print("[3] 群聊查找 ...", end=" ")
    try:
        token = get_tenant_token()
        chat_id = find_chat_id(token, GROUP_CHAT_NAME)
        if chat_id:
            print(f"✅ {GROUP_CHAT_NAME} ({chat_id})")
            results.append(("群聊", True, chat_id))

            # 4. 消息读取
            print("[4] 消息读取 ...", end=" ")
            try:
                msgs = list_recent_messages(token, chat_id, limit=1)
                print(f"✅ ({len(msgs)} 条)")
                results.append(("消息读取", True, ""))
            except Exception as e:
                print(f"❌ {e}")
                results.append(("消息读取", False, str(e)))
        else:
            print(f"⚠️  未找到群「{GROUP_CHAT_NAME}」，跳过后面的检查")
            results.append(("群聊", False, "未找到"))
    except Exception as e:
        print(f"❌ {e}")
        results.append(("群聊", False, str(e)))

    # 5. AI
    print("[5] AI ({}/{}) ...".format(AI_PROVIDER, AI_MODEL), end=" ")
    try:
        _, call_fn = _get_ai_client()
        resp = call_fn("回复：OK")
        if resp and len(resp) > 0:
            print(f"✅")
            results.append(("AI 连接", True, ""))
        else:
            print("⚠️  返回为空")
            results.append(("AI 连接", False, "返回为空"))
    except Exception as e:
        print(f"❌ {e}")
        results.append(("AI 连接", False, str(e)))

    # 6. Playwright
    if FETCH_METHOD == "playwright":
        print("[6] Playwright ...", end=" ")
        try:
            from playwright.sync_api import sync_playwright
            import os as _os
            _os.makedirs(PLAYWRIGHT_USER_DATA, exist_ok=True)
            with sync_playwright() as p:
                ctx = p.chromium.launch_persistent_context(
                    user_data_dir=PLAYWRIGHT_USER_DATA,
                    headless=True,
                    args=["--no-sandbox"],
                )
                # 检查是否已登录（看 cookie 里有没有小红书相关域）
                cookies = ctx.cookies()
                xhs_cookies = [c for c in cookies if "xiaohongshu" in c.get("domain", "")]
                ctx.close()
                if xhs_cookies:
                    print(f"✅ 已登录（{len(xhs_cookies)} 个小书 cookie）")
                    results.append(("Playwright", True, ""))
                else:
                    print("⚠️  未登录，请运行 --login-xhs")
                    results.append(("Playwright", False, "未登录"))
        except ImportError:
            print("⚠️  未安装 playwright")
            results.append(("Playwright", False, "未安装"))
        except Exception as e:
            print(f"❌ {e}")
            results.append(("Playwright", False, str(e)))

    # 汇总
    print("\n" + "=" * 60)
    print("📊 自检结果")
    print("=" * 60)
    all_ok = True
    for name, ok, detail in results:
        status = "✅" if ok else ("⚠️" if "未" in detail else "❌")
        detail_str = f" — {detail}" if detail else ""
        print(f"  {status} {name}{detail_str}")
        if not ok and "未" not in detail:  # "未安装"/"未登录"/"未找到" 不算致命错误
            all_ok = False

    if all_ok:
        print("\n✅ 所有核心组件正常，可以运行 python main.py")
    else:
        print("\n⚠️  部分组件异常，请根据上面的错误信息排查")

    print("=" * 60)


# ============================================================
# 入口
# ============================================================

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] in ("--check", "--diagnose", "-d"):
        check_all()
    elif len(sys.argv) > 1 and sys.argv[1] in ("--list", "--discover", "-l"):
        list_tables()
    elif len(sys.argv) > 1 and sys.argv[1] in ("--collect", "--msg", "-c"):
        collect_messages()
    elif len(sys.argv) > 1 and sys.argv[1] in ("--login-xhs", "--login"):
        login_xiaohongshu()
    else:
        process_all()
