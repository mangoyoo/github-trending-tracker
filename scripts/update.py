#!/usr/bin/env python3
"""
🔥 GitHub Star Growth Tracker
每日追踪 GitHub 上 star 增长最快的项目，找出真正的"今日之星"。
"""

import json
import os
import sys
import time
import traceback
from datetime import datetime, timedelta
from pathlib import Path

# ── 配置 ──────────────────────────────────────────────
DATA_DIR = Path("data")
HISTORY_DIR = DATA_DIR / "history"
TRACKED_REPOS_FILE = DATA_DIR / "tracked_repos.json"
LATEST_FILE = DATA_DIR / "latest.json"
README_FILE = Path("README.md")

# 从环境变量读取 GitHub Token（GitHub Actions 自动注入）
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")

# 每次 API 请求之间等待（秒），避免触发 rate limit
API_DELAY = 0.5


# ── 工具函数 ──────────────────────────────────────────

def log(msg: str):
    """带时间戳的日志输出"""
    t = datetime.now().strftime("%H:%M:%S")
    print(f"[{t}] {msg}")


def api_headers() -> dict:
    headers = {"Accept": "application/vnd.github.v3+json"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    return headers


def git_api_get(url: str) -> dict | None:
    """对 GitHub API 发起 GET 请求，带重试和 rate-limit 处理"""
    import requests

    for attempt in range(3):
        try:
            resp = requests.get(url, headers=api_headers(), timeout=15)
            if resp.status_code == 403:
                log("⚠️  API rate limit 或权限不足，等待后重试...")
                time.sleep(30)
                continue
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            log(f"⚠️  API 请求失败 (attempt {attempt + 1}/3): {e}")
            if attempt < 2:
                time.sleep(5)

    log("❌ API 请求最终失败，跳过")
    return None


# ── 核心逻辑 ──────────────────────────────────────────

def fetch_trending_repos() -> list[dict]:
    """
    从 GitHub Search API 抓取热门项目。
    策略：过去 7 天有推送 + stars > 100，按 stars 降序。
    """
    since = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    query = f"stars:>100 pushed:>={since}"
    url = f"https://api.github.com/search/repositories?q={query}&sort=stars&order=desc&per_page=100"

    log(f"🔍 搜索: {query}")
    data = git_api_get(url)
    if not data:
        return []

    repos = []
    for item in data.get("items", []):
        repos.append({
            "repo": item["full_name"],
            "name": item["name"],
            "stars": item["stargazers_count"],
            "language": item.get("language") or "Unknown",
            "description": (item.get("description") or "")[:200],
            "url": item["html_url"],
            "topics": item.get("topics", []),
            "created_at": item.get("created_at", ""),
            "updated_at": item.get("updated_at", ""),
            "pushed_at": item.get("pushed_at", ""),
        })

    # 再补充获取 tracked_repos.json 中的固定项目（确保不会漏掉）
    tracked = load_tracked_repos()
    tracked_missing = [t for t in tracked if not any(r["repo"] == t["repo"] for r in repos)]
    if tracked_missing:
        log(f"📡 补充获取 {len(tracked_missing)} 个追踪项目...")
        for t in tracked_missing:
            time.sleep(API_DELAY)
            data = git_api_get(f"https://api.github.com/repos/{t['repo']}")
            if data:
                repos.append({
                    "repo": data["full_name"],
                    "name": data["name"],
                    "stars": data["stargazers_count"],
                    "language": data.get("language") or "Unknown",
                    "description": (data.get("description") or "")[:200],
                    "url": data["html_url"],
                    "topics": data.get("topics", []),
                })
                log(f"  ✅ {t['repo']}: {data['stargazers_count']} stars")
            else:
                log(f"  ⚠️  无法获取 {t['repo']}")

    log(f"📊 共获取 {len(repos)} 个项目")
    return repos


def load_previous_snapshot(date_str: str) -> list[dict] | None:
    """加载指定日期的历史快照"""
    path = HISTORY_DIR / f"{date_str}.json"
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f).get("snapshot", [])


def load_tracked_repos() -> list[dict]:
    """加载固定追踪列表"""
    if not TRACKED_REPOS_FILE.exists():
        return []
    with open(TRACKED_REPOS_FILE, encoding="utf-8") as f:
        return json.load(f)


def calculate_growth(current: list[dict], previous: list[dict]) -> list[dict]:
    """计算每个项目的 star 增长量"""
    prev_map = {r["repo"]: r["stars"] for r in previous}

    for repo in current:
        key = repo["repo"]
        cur = repo["stars"]
        prev = prev_map.get(key)

        if prev is None:
            repo["growth_24h"] = 0
            repo["growth_24h_percent"] = 0.0
            repo["status"] = "NEW"
        else:
            growth = cur - prev
            percent = round((growth / prev * 100) if prev > 0 else 0.0, 2)
            repo["growth_24h"] = growth
            repo["growth_24h_percent"] = percent
            repo["status"] = "TRACKING"

    return current


def generate_zh_intro(repo: dict) -> str:
    """生成简短的中文项目介绍"""
    name = repo["name"]
    desc = repo["description"]
    lang = repo["language"]

    # 手动映射一批常见热门项目
    KNOWN = {
        "freeCodeCamp": "免费编程学习平台，提供完整 Web 开发课程和证书",
        "free-programming-books": "免费编程书籍合集，涵盖多种语言和主题",
        "developer-roadmap": "开发者学习路线图，帮助规划职业发展",
        "awesome-python": "Python 精选资源与工具列表",
        "react": "Facebook 出品的 JavaScript UI 库",
        "linux": "Linux 操作系统内核",
        "computer-science": "计算机科学自学课程（OSSU）",
        "tensorflow": "Google 的机器学习框架",
        "ohmyzsh": "Zsh shell 的框架和插件管理器",
        "n8n": "开源工作流自动化工具",
        "vscode": "微软开发的免费代码编辑器",
        "AutoGPT": "自主 AI 智能体，可自动完成复杂任务",
        "flutter": "Google 的跨平台 UI 工具包",
        "bootstrap": "流行的前端 CSS 框架",
        "gitignore": "各种编程语言的 .gitignore 模板集合",
        "awesome-go": "Go 语言精选资源列表",
        "ollama": "本地运行大语言模型的工具",
        "openclaw": "个人 AI 助手框架，多平台部署 🦞",
        "claw-code": "AI 驱动的代码编辑助手",
    }
    if name in KNOWN:
        return KNOWN[name]

    if name.startswith("awesome-"):
        lang_name = name.removeprefix("awesome-").title()
        return f"{lang_name} 精选资源列表"

    if desc:
        return f"{lang} 项目：{desc[:100]}"

    return f"{lang} 项目"


def save_snapshot(date_str: str, snapshot: list[dict]):
    """保存当前快照到历史文件和 latest"""
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)

    payload = {"date": date_str, "updated_at": datetime.now().isoformat(), "snapshot": snapshot}

    # 历史快照
    history_file = HISTORY_DIR / f"{date_str}.json"
    with open(history_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    # 最新快照
    with open(LATEST_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    log(f"💾 已保存 {len(snapshot)} 条数据")


def generate_readme(date_str: str, snapshot: list[dict]):
    """生成 README.md ── 即仓库首页展示内容"""
    # 按 24h 增长量排序（降序），取 Top 30
    sorted_repos = sorted(snapshot, key=lambda x: x["growth_24h"], reverse=True)[:30]

    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    lines = [
        "# 🔥 GitHub Star 增长最快项目追踪",
        "",
        f"> 📅 数据更新于 {now}（每日自动更新）",
        "",
        "## 📈 Top 30（按 24 小时 Star 增长量）",
        "",
        "| 排名 | 项目 | 语言 | Stars | 24h 增长 | 状态 |",
        "|------|------|------|-------|---------|------|",
    ]

    for i, repo in enumerate(sorted_repos, 1):
        growth = repo["growth_24h"]
        percent = repo["growth_24h_percent"]

        if growth > 500:
            icon = "🚀"
        elif growth > 100:
            icon = "📈"
        elif growth > 0:
            icon = "📊"
        else:
            icon = "➖"

        status_map = {"NEW": "✨", "TRACKING": "👁️"}
        status_icon = status_map.get(repo["status"], "❓")

        if growth > 0:
            growth_cell = f"+{growth} ({percent}%) {icon}"
        else:
            growth_cell = f"{growth} ➖"

        lines.append(
            f"| {i} | [{repo['repo']}]({repo['url']}) | {repo['language']} | "
            f"{repo['stars']:,} | {growth_cell} | {status_icon} |"
        )

    lines.extend([
        "",
        "---",
        "",
        "## 📊 统计信息",
        "",
        f"- 共追踪 **{len(snapshot)}** 个项目",
        f"- 今日有增长的项目：**{sum(1 for r in sorted_repos if r['growth_24h'] > 0)}** 个",
        f"- 新增项目：**{sum(1 for r in sorted_repos if r['status'] == 'NEW')}** 个",
        "",
        "## ℹ️ 关于",
        "",
        "- 🔗 数据来源：GitHub Search API + Repo API",
        "- 🔄 更新频率：每日 12:00 (GMT+8) 自动更新",
        "- 📁 历史数据：`data/history/` 目录",
        "- ⭐ 筛选条件：stars > 100 且近 7 天有提交",
        "- 📂 固定追踪：`data/tracked_repos.json`",
        "",
        "---",
        "",
        "*本页面由 GitHub Actions 自动生成，数据仅供参考。*",
    ])

    with open(README_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    log(f"📝 README.md 已更新 ({len(sorted_repos)} 条)")


# ── 主流程 ────────────────────────────────────────────

def main():
    """每日更新主流程"""
    # 切换到仓库根目录
    os.chdir(Path(__file__).parent.parent)

    today = datetime.now().strftime("%Y-%m-%d")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    log(f"🔥 开始更新 ({today})")

    # 1. 获取当前热门项目
    current = fetch_trending_repos()
    if not current:
        log("❌ 未获取到任何项目，终止")
        sys.exit(1)

    # 2. 加载历史数据计算增长
    log(f"📂 加载历史 ({yesterday})...")
    prev = load_previous_snapshot(yesterday)
    if prev:
        log(f"✅ 找到 {len(prev)} 条历史数据")
    else:
        log("ℹ️  首次运行，尚无历史数据（明天开始会有增长对比）")

    # 3. 计算增长
    current = calculate_growth(current, prev or [])

    # 4. 生成中文介绍
    for repo in current:
        repo["zh_intro"] = generate_zh_intro(repo)

    # 5. 保存数据
    save_snapshot(today, current)

    # 6. 生成 README
    generate_readme(today, current)

    # 7. 输出摘要
    sorted_repos = sorted(current, key=lambda x: x["growth_24h"], reverse=True)[:10]
    log("🔥 今日增长 Top 10:")
    for i, r in enumerate(sorted_repos, 1):
        if r["growth_24h"] > 0:
            log(f"   {i}. {r['repo']} +{r['growth_24h']} ({r['growth_24h_percent']}%)")
        else:
            log(f"   {i}. {r['repo']} (新增，待对比)")

    log(f"🎉 更新完成！({today})")


if __name__ == "__main__":
    main()
