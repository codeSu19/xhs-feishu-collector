# GitHub 上传与维护指南

## 一、检查哪些文件会被上传

项目里有两类文件：

| 会上传 | 不会上传（gitignore 排除） |
|--------|--------------------------|
| main.py | config.py（含你的真实 Key） |
| config.example.py（模板） | xhs_browser_profile/（登录态） |
| requirements.txt | __pycache__/ |
| README.md | .idea/ |
| ios-shortcut-guide.md | |
| LICENSE | |
| .gitignore | |

---

## 二、安装 Git

```powershell
# 下载安装：https://git-scm.com/download/win
# 安装后验证：
git --version
```

---

## 三、初始化并提交

```powershell
cd D:\Project\xhs-feishu

# 初始化 Git 仓库
git init

# 添加所有文件（.gitignore 会自动排除 config.py 等）
git add .

# 查看哪些文件会被提交（确认 config.py 不在列表里）
git status

# 首次提交
git commit -m "🎉 初始提交：小红书笔记采集工具"
```

---

## 四、上传到 GitHub

### 4.1 在 GitHub 创建仓库

```
1. 打开 https://github.com
2. 登录 → 右上角 + → New repository
3. Repository name: xhs-feishu-collector
4. Description: 小红书笔记一键采集到飞书表格，AI 自动分析
5. 选 Public 或 Private
6. 不要勾选 "Add a README file"（我们已经有一个了）
7. 点 "Create repository"
```

### 4.2 推送代码

创建仓库后会跳转到一个页面，显示类似以下命令：

```powershell
# 添加远程仓库地址（换成你自己的）
git remote add origin https://github.com/你的用户名/xhs-feishu-collector.git

# 推送到 GitHub
git branch -M main
git push -u origin main
```

以后每次 push 可能需要输入 GitHub 用户名和密码（或用 Personal Access Token）。

> **推荐**：用 GitHub CLI 或 SSH Key 可以免密码推送。
> ```powershell
> # 安装 GitHub CLI: https://cli.github.com
> gh auth login
> git push -u origin main
> ```

---

## 五、日常维护流程

### 5.1 修改代码后如何同步

```powershell
# 1. 查看改了哪些文件
git status

# 2. 添加改动
git add main.py              # 添加指定文件
# 或
git add .                    # 添加所有改动

# 3. 提交
git commit -m "修复：优化 Playwright 抓取选择器"

# 4. 推送到 GitHub
git push
```

### 5.2 commit message 规范

```
feat: 新功能      feat: 支持 Playwright 登录态抓取
fix: 修复 bug     fix: 修复 page_token 为空时 API 报错
docs: 文档更新    docs: 更新快捷指令教程
refactor: 重构    refactor: 提取内容清洗函数
```

### 5.3 不想上传某次改动？

改完 `config.py` 后又不想泄露真实 Key：

```powershell
# config.py 已经在 .gitignore 里，不会被跟踪
# 如果不小心改了被跟踪的文件想撤销：
git checkout -- 文件名
```

### 5.4 误提交了敏感文件怎么办

```powershell
# 从 Git 历史中删除（但保留本地文件）
git rm --cached config.py
git commit -m "移除敏感文件"
git push

# 如果已经 push 了多次，建议直接换 Key（更安全）
```

---

## 六、常用 Git 命令速查

| 命令 | 作用 |
|------|------|
| `git status` | 查看文件改动状态 |
| `git diff` | 查看具体改了什么 |
| `git log --oneline` | 查看提交历史 |
| `git add .` | 暂存所有改动 |
| `git commit -m "消息"` | 提交 |
| `git push` | 推送到 GitHub |
| `git pull` | 拉取远程更新 |
| `git checkout -b 分支名` | 创建新分支 |
| `git merge 分支名` | 合并分支 |

---

## 七、PyCharm 用户

PyCharm 自带 Git 集成：

```
1. VCS → Enable Version Control Integration → 选 Git
2. 工具栏会出现 Git 按钮
3. Commit 面板：Ctrl+K
4. Push 面板：Ctrl+Shift+K
5. 改动的文件会高亮显示
```

在 PyCharm 里可以完全不用命令行操作 Git。
