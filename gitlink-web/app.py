#!/usr/bin/env python3
"""GitLink Skills Web Service — 严格遵循 SKILL.md 工作流"""

import os, re, json, subprocess, time, traceback
from pathlib import Path
from flask import Flask, request, jsonify, render_template
import requests

NOW = time.strftime("%Y-%m-%d")  # 当前日期，注入所有prompt防止幻觉

app = Flask(__name__)

NOW = time.strftime("%Y-%m-%d")  # 当前日期，注入所有 prompt 防止幻觉

API_KEY = os.environ.get("API_KEY") or ""
if not API_KEY:
    # 本地测试用
    API_KEY = "<YOUR_API_KEY>"
API_BASE = os.environ.get("API_BASE", "https://api.deepseek.com/v1")
API_MODEL = os.environ.get("API_MODEL", "deepseek-chat")
SKILL_DIR = Path(__file__).parent / "skills"
HISTORY_DIR = Path(__file__).parent / "reports"
HISTORY_DIR.mkdir(exist_ok=True)

SKILL_NAMES = {
    "research": "research-tracker",
    "contributor": "contributor-insight",
    "issue-triage": "issue-triage",
    "ci-health": "ci-health",
    "repo-health": "repo-health",
    "pr-analytics": "pr-analytics",
    "cross-search": "cross-search",
    "user-analysis": "user-analysis",
    "repo-compare": "repo-compare",
    "lab-hotspot": "lab-hotspot",
    "lab-insight": "lab-insight",
    "lab-compliance": "lab-compliance",
    "lab-match": "lab-match",
    "lab-track": "lab-track",
}

SKILL_INFO = {
    "research-tracker": {"title":"技术调研","label":"研究主题","placeholder":"大模型、AI Agent、微服务","intro":"输入一个研究主题，自动拆解为多个关键词在 GitLink 上搜索相关项目，深度评估后生成调研报告。","output_desc":"热点概览（项目数/语言/活跃度）\n项目排行榜（含评分/星数/Fork/链接）\n重点分析（核心项目详情）\n趋势洞察与建议"},
    "contributor-insight":{"title":"贡献者分析","label":"仓库(owner/repo)","placeholder":"ci4s/ci4sManagement-cloud","intro":"输入仓库地址，分析贡献者的活跃度、贡献趋势和团队健康度。","output_desc":"团队概览（贡献者总数/级别分布）\n活跃度排行榜（PR数/Issue数/趋势）\n重点贡献者分析（画像/PR明细）\n团队健康度评估与建议"},
    "issue-triage":{"title":"Issue分拣","label":"仓库(owner/repo)","placeholder":"Gitlink/gitlink-cli","intro":"输入仓库地址，自动扫描 Issue 并分类（Bug/Feature/Question），评估紧急度和复杂度。","output_desc":"Issue总览（总数/开放/已关闭）\n类型分类（Bug/Feature/Docs等）\n紧急度评估（Urgent/High/Normal/Low）\n行动建议（FixNow/Investigate/Discuss）\n维护建议"},
    "ci-health":{"title":"CI健康巡检","label":"仓库(owner/repo)","placeholder":"jiangtx/gitlink-cli","intro":"检查仓库 CI/CD 状态（open_devops）、构建历史、成功率。","output_desc":"健康度总览（CI激活/成功率/稳定性评分）\n构建趋势（近7天/14天/30天）\n故障分析与改进建议"},
    "repo-health":{"title":"仓库健康巡检","label":"仓库(owner/repo)","placeholder":"Gitlink/gitlink-cli","intro":"综合评估仓库的活跃度、社区规模、代码产出和风险。","output_desc":"基本信息（语言/规模/描述）\n活跃度分析（PR/Issue统计）\nPR/Issue健康度\n综合评分与改进建议"},
    "pr-analytics":{"title":"PR效率分析","label":"仓库(owner/repo)","placeholder":"Gitlink/gitlink-cli","intro":"统计 PR 吞吐量、合并率、贡献者活跃度。","output_desc":"PR吞吐量（总数/合并/关闭）\n合并效率分析\n贡献者排行榜\n改进建议"},
    "cross-search":{"title":"跨维搜索","label":"搜索主题","placeholder":"AI Agent、数据分析、容器","intro":"同时搜索 GitLink 的仓库、代码和 Issue 三个维度。","output_desc":"各维度命中概况\n仓库搜索结果\n代码片段摘要\nIssue讨论热点"},
    "user-analysis":{"title":"用户分析","label":"用户名","placeholder":"jiangtx、lindiwen23","intro":"查看用户基本信息、活跃度、项目参与情况。","output_desc":"基本信息（注册时间/身份/项目数）\n活跃度分析\n项目贡献列表\n综合用户画像"},
    "repo-compare":{"title":"仓库对比","label":"AvsB","placeholder":"Gitlink/gitlink-cli vs ci4s/ci4sManagement-cloud","intro":"对比两个仓库的指标差异。","output_desc":"基本信息对比（语言/规模/分支）\n社区活跃度对比\n开发活动对比（PR/Issue/Release）\n综合结论"},
    "lab-hotspot":{"title":"热点追踪","label":"研究主题","placeholder":"大模型、AI Agent、微服务","intro":"多关键词搜索GitLink项目，深度评估+领域知识图谱。","output_desc":"热点概览（项目数/语言/活跃比例）\n项目排行榜（评分/星数/Fork/链接）\n领域知识图谱（Mermaid流程图）\n趋势洞察与建议"},
    "lab-insight":{"title":"项目洞悉","label":"仓库(owner/repo)","placeholder":"ci4s/ci4sManagement-cloud","intro":"综合仓库信息+贡献者+PR/Issue生成全息分析。","output_desc":"项目概况（描述/规模/语言）\n社区活跃度（贡献者/PR/Issue）\n团队画像\n综合健康度评估"},
    "lab-compliance":{"title":"合规检查","label":"仓库(owner/repo)","placeholder":"Gitlink/gitlink-cli","intro":"检查License/CI/文档完整性，输出合规评分。","output_desc":"License合规性\n文档完整性\nCI/CD完善度\n可复现性检查\n综合评分"},
    "lab-match":{"title":"协作匹配","label":"仓库(owner/repo)","placeholder":"ci4s/ci4sManagement-cloud","intro":"分析Issue和社区健康度，评估新手友好度。","output_desc":"项目概览（技术栈/社区规模）\n入门友好度分析\n推荐贡献方向\n社区活跃度评估"},
    "lab-track":{"title":"进度跟踪","label":"仓库列表(逗号分隔)","placeholder":"repo1,repo2,repo3","intro":"批量巡检多仓库，输出健康/警告/危险状态。","output_desc":"各仓库状态概览（健康/警告/危险）\n详细指标表（贡献者/CI/活跃度）\n预警详情\n整体健康度评估"},
}

# ── 工具函数 ──

def run(cmd, timeout=30):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        out = r.stdout.strip()
        if not out:
            return r.stderr.strip()[:1000]
        # JSON search results can be large, don't truncate too aggressively
        return out[:50000]
    except subprocess.TimeoutExpired:
        return "[超时]"
    except Exception as e:
        return f"[错误] {e}"


def llm(messages, max_tokens=8192):
    if not API_KEY:
        return "【API_KEY 未设置】"
    try:
        resp = requests.post(
            f"{API_BASE}/chat/completions",
            headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
            json={"model": API_MODEL, "messages": messages, "max_tokens": max_tokens, "temperature": 0.7},
            timeout=180
        )
        data = resp.json()
        if "choices" in data and data["choices"]:
            return data["choices"][0]["message"]["content"]
        return f"[API异常] {json.dumps(data, ensure_ascii=False)[:300]}"
    except Exception as e:
        return f"[请求失败] {e}"


def load_prompt(name):
    p = SKILL_DIR / f"{name}.txt"
    return p.read_text(encoding="utf-8") if p.exists() else ""


# ═══════════════════════════════════════════════════════════════════
# research-tracker：严格遵循 SKILL.md 5步工作流
# Round 1: LLM 拆关键词  →  服务器执行搜索+深度评估  →  Round 2: LLM 写报告
# ═══════════════════════════════════════════════════════════════════

def agent_research(user_input):
    steps = []  # 记录每一步供对比

    # ── Step 1: LLM 拆解关键词 ──
    kw_prompt = f"""你是一个科研助手。请为研究主题「{user_input}」拆解 3~5 个搜索关键词。
要求：覆盖中英文、缩写全称、技术术语和行业叫法。
直接返回关键词列表，每行一个，不要多余文字。"""
    kw_response = llm([{"role": "user", "content": kw_prompt}])
    keywords = [l.strip("-* \t") for l in kw_response.strip().split("\n") if l.strip()]
    steps.append(("Step1-关键词拆解", {"prompt": kw_prompt, "llm_output": kw_response, "keywords": keywords}))

    # ── Step 2: 多关键词搜索 ──
    all_projects = {}
    raw_searches = []
    for kw in keywords[:5]:
        out = run(f'gitlink-cli search +repos -k "{kw}" --format json')
        raw_searches.append(f"--- {kw} ---\n{out}")
        try:
            for p in json.loads(out).get("data", {}).get("projects", []):
                key = f"{p['author']['login']}/{p['identifier']}"
                if key not in all_projects:
                    all_projects[key] = {"search_data": p, "keywords": [kw]}
                else:
                    all_projects[key]["keywords"].append(kw)
        except:
            pass
    steps.append(("Step2-多关键词搜索", {"keyword_count": len(keywords), "raw_hits": sum(1 for k in keywords), "unique": len(all_projects)}))

    # ── Step 3: 去重 + 深度评估 ──
    sorted_projects = sorted(all_projects.values(), key=lambda x: x["search_data"].get("praises_count", 0), reverse=True)[:8]
    deep_data = []
    seen_mirror = 0
    for p in sorted_projects:
        sd = p["search_data"]
        owner, repo_name = sd["author"]["login"], sd["identifier"]
        info = run(f'gitlink-cli repo +info --owner {owner} --repo {repo_name} --format json')
        is_mirror = False
        try:
            info_data = json.loads(info)
            is_mirror = info_data.get("data", {}).get("mirror", False)
            if is_mirror:
                seen_mirror += 1
        except:
            pass
        url = f"https://www.gitlink.org.cn/{owner}/{repo_name}"
        deep_data.append(f"# [{owner}/{repo_name}]({url})\nURL: {url}\n关键词: {', '.join(p['keywords'])}\n镜像: {'是' if is_mirror else '否'}\n{info}")
    steps.append(("Step3-深度评估", {"deep_count": len(deep_data), "mirror_count": seen_mirror}))

    # ── Step 4+5: LLM 写报告 ──
    system = load_prompt("research-tracker")
    real_data = "=== 搜索结果 ===\n" + "\n\n".join(raw_searches) + "\n\n=== 深度评估 ===\n" + "\n\n".join(deep_data)
    report_prompt = f"""研究主题: {user_input}
搜索关键词: {', '.join(keywords)}

以下是从 GitLink 平台实时获取的真实数据。
请基于这些数据，严格按照 SKILL.md 的评分标准和模板生成调研报告。
包含：技术格局概览、项目成熟度排行榜（含评分）、重点分析、趋势洞察、调研建议。

**【超链接要求】**：报告中所有项目名必须使用 Markdown 超链接格式：
  - 格式：[owner/repo](https://www.gitlink.org.cn/owner/repo)
  - 排行榜、重点分析、推荐表中所有仓库名都必须是可点击的超链接
  - 例如：[Gitlink/microservices](https://www.gitlink.org.cn/Gitlink/microservices)
  - 镜像项目也加链接：[owner/repo](https://...)

{real_data}"""
    report = llm([
        {"role": "system", "content": system},
        {"role": "user", "content": report_prompt}
    ])
    steps.append(("Step4+5-报告生成", {"llm_input_chars": len(report_prompt), "report_chars": len(report)}))

    return report, steps


# ═══════════════════════════════════════════════════════════════════
# contributor-insight：严格遵循 SKILL.md 5步工作流
# 服务器执行命令 → LLM 分析写报告
# ═══════════════════════════════════════════════════════════════════

def agent_contributor(user_input):
    steps = []
    parts = user_input.replace(" ", "").split("/")
    if len(parts) < 2:
        return "请提供 owner/repo 格式", []
    owner, repo_name = parts[0], parts[1]

    # Step 1: repo +info
    info = run(f'gitlink-cli repo +info --owner {owner} --repo {repo_name} --format json')
    steps.append(("Step1-项目概览", {"raw_len": len(info)}))
    try:
        contrib_count = json.loads(info).get("data", {}).get("contributor_users_count", 0)
    except:
        contrib_count = "?"

    # Step 2: pr +list + issue +list
    pr_data = run(f'gitlink-cli pr +list --owner {owner} --repo {repo_name} --format json')
    issue_data = run(f'gitlink-cli issue +list --owner {owner} --repo {repo_name} --format json')
    steps.append(("Step2-数据采集", {"pr_len": len(pr_data), "issue_len": len(issue_data)}))

    # Step 3: user +info 提取画像
    authors = set()
    try:
        for i in json.loads(pr_data).get("data", {}).get("issues", []):
            if i.get("author_login"):
                authors.add(i["author_login"])
    except:
        pass
    user_infos = []
    for a in list(authors)[:5]:
        u = run(f'gitlink-cli user +info --login {a} --format json')
        user_infos.append(f"# {a}\n{u}")
    steps.append(("Step3-用户画像", {"author_count": len(authors)}))

    # Step 4+5: LLM 分析写报告
    system = load_prompt("contributor-insight")
    data = f"# repo +info\n{info}\n\n# pr +list\n{pr_data}\n\n# issue +list\n{issue_data}\n\n" + "\n".join(user_infos)
    prompt = f"""仓库: [{owner}/{repo_name}](https://www.gitlink.org.cn/{owner}/{repo_name})
实际贡献者(从PR提取): {', '.join(authors) if authors else '无'}
repo +info contributor_users_count: {contrib_count}

以下是 gitlink-cli 获取的真实数据。
请基于此生成贡献者洞察报告，包含：团队概览、活跃度排行榜、重点分析、健康度评估、建议。
仓库名用超链接: [owner/repo](https://www.gitlink.org.cn/owner/repo)。
如果数据缺失请如实标注，不要编造。

{data}"""
    report = llm([
        {"role": "system", "content": system},
        {"role": "user", "content": prompt}
    ])
    steps.append(("Step4+5-报告", {"llm_input": len(prompt), "report_len": len(report)}))
    return report, steps


# ═══════════════════════════════════════════════════════════════════
# issue-triage：严格遵循 SKILL.md 5步工作流
# ═══════════════════════════════════════════════════════════════════

def agent_issue(user_input):
    steps = []
    parts = user_input.replace(" ", "").split("/")
    if len(parts) < 2:
        return "请提供 owner/repo 格式", []
    owner, repo_name = parts[0], parts[1]

    # Step 1: repo +info
    info = run(f'gitlink-cli repo +info --owner {owner} --repo {repo_name} --format json')
    steps.append(("Step1-项目概览", {}))

    # Step 2: issue +list
    issues_raw = run(f'gitlink-cli issue +list --owner {owner} --repo {repo_name} --state open --format json')
    steps.append(("Step2-Issue列表", {"raw_len": len(issues_raw)}))

    # 客户端按 status_id 过滤
    open_issues = []
    try:
        for i in json.loads(issues_raw).get("data", {}).get("issues", []):
            sid = i.get("status_id", -1)
            if sid in (1, 2, 0):
                open_issues.append(i)
    except:
        pass
    steps.append(("Step2.5-状态过滤", {"before": "?", "after": len(open_issues)}))

    # Step 3: issue +view 逐条分析
    views = []
    for issue in open_issues[:10]:
        num = issue.get("project_issues_index") or issue.get("number", "")
        if num:
            v = run(f'gitlink-cli issue +view --owner {owner} --repo {repo_name} --number {num} --format json')
            views.append(f"# Issue #{num}: {issue.get('subject','')}\n{v}")
    steps.append(("Step3-逐条分析", {"count": len(views)}))

    # Step 4+5: LLM
    system = load_prompt("issue-triage")
    data = f"# repo +info\n{info}\n\n# issue +list (所有)\n{issues_raw}\n\n过滤后开放({len(open_issues)}条):\n" + "\n\n".join(views)
    prompt = f"""仓库: [{owner}/{repo_name}](https://www.gitlink.org.cn/{owner}/{repo_name})
过滤后开放Issue: {len(open_issues)}条
请按SKILL.md的4维分类规则生成分拣报告。
注意: --state open 过滤不准确, 已按 status_id(1=新增,2=处理中) 过滤, status_id=0已标注异常。
仓库名用超链接格式。
如果数据中有字段缺失请如实说。

{data}"""
    report = llm([
        {"role": "system", "content": system},
        {"role": "user", "content": prompt}
    ])
    steps.append(("Step4+5-报告", {"report_len": len(report)}))
    return report, steps


# ═══════════════════════════════════════════════════════════════════
# ci-health：严格遵循 SKILL.md 5步工作流
# ═══════════════════════════════════════════════════════════════════

def agent_ci(user_input):
    steps = []
    parts = user_input.replace(" ", "").split("/")
    if len(parts) < 2:
        return "请提供 owner/repo 格式", []
    owner, repo_name = parts[0], parts[1]

    # Step 1: repo +info → open_devops
    info = run(f'gitlink-cli repo +info --owner {owner} --repo {repo_name} --format json')
    open_devops = False
    try:
        d = json.loads(info).get("data", {})
        open_devops = d.get("open_devops", False)
    except:
        pass
    steps.append(("Step1-CI授权检查", {"open_devops": open_devops}))

    if not open_devops:
        return f"该仓库 CI/CD 未激活 (open_devops=false)。\n\n## repo 基本信息\n{info}\n\n建议在 GitLink Web 界面开启 DevOps 后重新巡检。", steps

    # Step 2: ci +builds
    builds = run(f'gitlink-cli ci +builds --owner {owner} --repo {repo_name} --format json')
    steps.append(("Step2-构建历史", {"builds_len": len(builds)}))

    # Step 3: ci +logs (失败构建)
    failed_ids = []
    try:
        for b in json.loads(builds).get("data", {}).get("builds", [])[:5]:
            if b.get("status") == "failed":
                failed_ids.append(b.get("id", ""))
    except:
        pass
    logs_data = []
    for bid in failed_ids[:3]:
        l = run(f'gitlink-cli ci +logs --owner {owner} --repo {repo_name} --build {bid} --format json')
        logs_data.append(f"# Build {bid}\n{l}")
    steps.append(("Step3-失败日志", {"failed_count": len(failed_ids)}))

    # Step 4+5: LLM
    system = load_prompt("ci-health")
    data = f"# repo +info\n{info}\n\n# ci +builds\n{builds}\n\n" + ("\n".join(logs_data) if logs_data else "# 无失败构建")
    prompt = f"""仓库: {owner}/{repo_name}
CI激活: {'是' if open_devops else '否'}
请生成 CI 健康巡检报告。包含：健康度总览、构建趋势、故障分析、改进建议。
open_devops=false 表示CI未激活，此时无构建数据。

{data}"""
    report = llm([
        {"role": "system", "content": system},
        {"role": "user", "content": prompt}
    ])
    steps.append(("Step4+5-报告", {"report_len": len(report)}))
    return report, steps


# ═══════════════════════════════════════════════════════════════════
# repo-health：仓库健康巡检 — 综合评估仓库活动、代码规模、社区参与
# ═══════════════════════════════════════════════════════════════════

def agent_repo_health(user_input):
    steps = []
    parts = user_input.replace(" ", "").split("/")
    if len(parts) < 2:
        return "请提供 owner/repo 格式", []
    owner, repo_name = parts[0], parts[1]

    # repo +info
    info = run(f'gitlink-cli repo +info --owner {owner} --repo {repo_name} --format json')
    steps.append(("Step1-基本信息", {"len": len(info)}))

    # issue +list + pr +list
    issues = run(f'gitlink-cli issue +list --owner {owner} --repo {repo_name} --format json')
    prs = run(f'gitlink-cli pr +list --owner {owner} --repo {repo_name} --format json')
    steps.append(("Step2-活动数据", {"issues_len": len(issues), "prs_len": len(prs)}))

    data = f"# repo +info\n{info}\n\n# issue +list\n{issues}\n\n# pr +list\n{prs}"
    report = llm([
        {"role": "system", "content": "你是一个仓库健康度评估专家。基于 gitlink-cli 获取的真实数据，评估仓库的综合健康度。"},
        {"role": "user", "content": f"""仓库: {owner}/{repo_name}

请基于以下真实数据生成仓库健康巡检报告，包含：
1. 仓库基本信息（语言、规模、创建时间）
2. 代码活跃度（Issue 数量、PR 数量、贡献者数）
3. PR/Issue 健康度（合并比例、开放比例）
4. 综合健康评分（满分 20）和风险提示

{data}"""}
    ])
    steps.append(("Step3-报告", {"len": len(report)}))
    return report, steps


# ═══════════════════════════════════════════════════════════════════
# pr-analytics：PR 效率分析 — 分析合并时间、Review 模式、贡献节奏
# ═══════════════════════════════════════════════════════════════════

def agent_pr_analytics(user_input):
    steps = []
    parts = user_input.replace(" ", "").split("/")
    if len(parts) < 2:
        return "请提供 owner/repo 格式", []
    owner, repo_name = parts[0], parts[1]

    # pr +list 获取全量
    all_prs = run(f'gitlink-cli pr +list --owner {owner} --repo {repo_name} --format json')
    steps.append(("Step1-PR列表", {"len": len(all_prs)}))

    # 提取统计
    total, merged, authors = 0, 0, set()
    try:
        for i in json.loads(all_prs).get("data", {}).get("issues", []):
            total += 1
            if i.get("pull_request_status") == 1:
                merged += 1
            if i.get("author_login"):
                authors.add(i["author_login"])
    except:
        pass
    steps.append(("Step2-统计", {"total": total, "merged": merged, "authors": len(authors)}))

    data = f"# pr +list\n{all_prs}"
    report = llm([
        {"role": "system", "content": "你是一个开源项目 PR 效率分析师。基于真实数据生成 PR 效率分析报告。"},
        {"role": "user", "content": f"""仓库: {owner}/{repo_name}
总 PR: {total}, 已合并: {merged}, 贡献者: {len(authors)}

请基于以下真实数据，生成 PR 效率分析报告，包含：
1. PR 吞吐量（总数、合并数、关闭数）
2. 贡献者活跃度（人均 PR 数、Top 贡献者）
3. 合并效率（合并比例）
4. 改进建议

{data}"""}
    ])
    steps.append(("Step3-报告", {"len": len(report)}))
    return report, steps


# ═══════════════════════════════════════════════════════════════════
# cross-search：跨维搜索 — 同时搜仓库、代码、Issue 并汇总
# ═══════════════════════════════════════════════════════════════════

def agent_cross_search(user_input):
    steps = []
    kw = user_input.strip()

    # 三维搜索
    repos = run(f'gitlink-cli search +repos -k "{kw}" --format json')
    code = run(f'gitlink-cli search +code -k "{kw}" --format json')
    issues = run(f'gitlink-cli search +issues -k "{kw}" --format json')
    steps.append(("Step1-三维搜索", {"repos_len": len(repos), "code_len": len(code), "issues_len": len(issues)}))

    # 统计
    repo_count, code_count, issue_count = 0, 0, 0
    try: repo_count = len(json.loads(repos).get("data",{}).get("projects",[]))
    except: pass
    try: code_count = len(json.loads(code).get("data",{}).get("results",[]))
    except: pass
    try: issue_count = len(json.loads(issues).get("data",{}).get("issues",[]))
    except: pass

    data = f"# 仓库搜索\n{repos}\n\n# 代码搜索\n{code}\n\n# Issue搜索\n{issues}"
    report = llm([
        {"role": "system", "content": "你是一个搜索分析师。汇总 GitLink 多维度搜索结果，生成综合分析报告。所有仓库名用 Markdown 超链接 [owner/repo](https://www.gitlink.org.cn/owner/repo) 格式。"},
        {"role": "user", "content": f"""搜索关键词: {kw}
仓库命中: {repo_count}  代码命中: {code_count}  Issue命中: {issue_count}

请基于以下搜索数据生成综合分析报告，包含：
1. 各维度命中概况
2. 仓库搜索结果分析
3. 代码搜索结果提炼（热门代码片段）
4. Issue 讨论热点
5. 综合洞察

{data}"""}
    ])
    steps.append(("Step2-报告", {"len": len(report)}))
    return report, steps


# ═══════════════════════════════════════════════════════════════════
# user-analysis：用户分析 — 搜索用户 + 查看用户信息
# ═══════════════════════════════════════════════════════════════════

def agent_user_analysis(user_input):
    steps = []
    login = user_input.strip()

    # 搜索用户
    search = run(f'gitlink-cli search +users -k "{login}" --format json')
    steps.append(("Step1-用户搜索", {"len": len(search)}))

    # 用户信息
    info = run(f'gitlink-cli user +info --login {login} --format json')
    steps.append(("Step2-用户信息", {"len": len(info)}))

    data = f"# search +users\n{search}\n\n# user +info\n{info}"
    report = llm([
        {"role": "system", "content": "你是一个用户分析专家。基于 GitLink 用户数据生成用户分析报告。"},
        {"role": "user", "content": f"""用户名: {login}

请基于以下真实数据生成用户分析报告：
1. 用户基本信息（注册时间、身份、项目数）
2. 用户活跃度（参与项目、关注数）
3. 搜索匹配情况
4. 综合画像

{data}"""}
    ])
    steps.append(("Step3-报告", {"len": len(report)}))
    return report, steps


# ═══════════════════════════════════════════════════════════════════
# repo-compare：仓库对比 — 对比两个仓库的核心指标
# ═══════════════════════════════════════════════════════════════════

def agent_repo_compare(user_input):
    steps = []
    # 解析 "A vs B" 格式
    parts = [p.strip() for p in user_input.replace("vs", " vs ").split("vs") if p.strip()]
    if len(parts) < 2:
        return "请用 A vs B 格式输入两个仓库，例如：Gitlink/gitlink-cli vs ci4s/ci4sManagement-cloud", []
    repo_a, repo_b = parts[0], parts[1]
    o1, r1 = repo_a.replace(" ", "").split("/")[:2]
    o2, r2 = repo_b.replace(" ", "").split("/")[:2]

    info_a = run(f'gitlink-cli repo +info --owner {o1} --repo {r1} --format json')
    info_b = run(f'gitlink-cli repo +info --owner {o2} --repo {r2} --format json')
    steps.append(("Step1-获取数据", {"repo_a_len": len(info_a), "repo_b_len": len(info_b)}))

    data = f"# 仓库A: [{repo_a}](https://www.gitlink.org.cn/{repo_a})\n{info_a}\n\n# 仓库B: [{repo_b}](https://www.gitlink.org.cn/{repo_b})\n{info_b}"
    report = llm([
        {"role": "system", "content": "你是一个仓库对比分析师。对比两个 GitLink 仓库的指标异同。报告中所有仓库名必须用 Markdown 超链接 [owner/repo](https://www.gitlink.org.cn/owner/repo) 格式。"},
        {"role": "user", "content": f"""仓库A: {repo_a}
仓库B: {repo_b}

请基于真实数据生成仓库对比报告：
1. 基本信息对比（语言、规模、分支）
2. 社区活跃度对比（贡献者、watch、fork）
3. 开发活动对比（PR、Issue、Release）
4. 综合结论与推荐

{data}"""}
    ])
    steps.append(("Step2-报告", {"len": len(report)}))
    return report, steps


# ═══════════════════════════════════════════════════════════════════
# 科研实验室：5 个科研场景工作流
# ═══════════════════════════════════════════════════════════════════

def lab_hotspot(user_input):
    """热点追踪+知识图谱：搜项目 → 深度评估 → 提取Fork关系链"""
    steps = []
    # 拆关键词
    kw_resp = llm([{"role": "user", "content": f"为研究主题「{user_input}」拆 3~5 个搜索关键词，每行一个"}])
    kws = [l.strip("-* \t") for l in kw_resp.strip().split("\n") if l.strip()][:5]
    steps.append(("Step1-关键词拆解", {"kws": kws}))

    # 搜索
    all_p = {}
    for kw in kws:
        out = run(f'gitlink-cli search +repos -k "{kw}" --format json')
        try:
            for p in json.loads(out).get("data",{}).get("projects",[]):
                k = f"{p['author']['login']}/{p['identifier']}"
                all_p.setdefault(k, {"data": p, "kws": []})["kws"].append(kw)
        except: pass
    steps.append(("Step2-搜索", {"unique": len(all_p)}))

    # 深度评估 + 提取 fork 关系
    sorted_p = sorted(all_p.values(), key=lambda x: x["data"].get("praises_count",0), reverse=True)[:8]
    deep, relations = [], []
    for p in sorted_p:
        sd = p["data"]; owner, repo = sd["author"]["login"], sd["identifier"]
        info = run(f'gitlink-cli repo +info --owner {owner} --repo {repo} --format json')
        try:
            d = json.loads(info).get("data",{})
            mirror = d.get("mirror",False)
            fork_from = d.get("forked_from_project_id")
            url = f"https://www.gitlink.org.cn/{owner}/{repo}"
            deep.append(f"[{owner}/{repo}]({url})\n关键词: {', '.join(p['kws'])}\n镜像: {mirror}\nFork来源: {fork_from}\n{info}")
            # 知识图谱关系
            if fork_from:
                relations.append(f"{owner}/{repo} → Fork了 → 项目ID {fork_from}")
            if d.get("fork_info"):
                parent = d["fork_info"].get("fork_form_name","?")
                relations.append(f"{owner}/{repo} → Fork自 → {d['fork_info'].get('fork_project_user_login','?')}/{parent}")
        except: pass
    steps.append(("Step3-深度评估+Fork图谱", {"deep": len(deep), "relations": len(relations)}))

    data = "=== 搜索结果 ===\n" + "\n".join([f"--- {kw} ---\n{run(f'gitlink-cli search +repos -k \"{kw}\" --format json')}" for kw in kws]) + "\n\n=== Fork关系 ===\n" + "\n".join(relations) + "\n\n=== 深度评估 ===\n" + "\n".join(deep)
    report = llm([
        {"role": "system", "content": "你是一个科研热点分析师。基于 GitLink 真实数据生成热点追踪+知识图谱报告。"},
        {"role": "user", "content": f"""当前日期: {NOW}
研究主题: {user_input}
关键词: {', '.join(kws)}

请生成报告（日期写「{NOW}」）：
1. 热点概览（项目数、语言、活跃项目比例）
2. 项目排行榜（含成熟度评分，仓库名用超链接）
3. **领域知识图谱**：用 Mermaid 流程图画出该研究领域的知识结构图，包含核心概念、子方向、关键技术及其关系（不是项目Fork关系，而是学术概念之间的关系）
4. 趋势洞察与建议

Mermaid 知识图谱示例格式（使用纯文本，不要用 HTML 标签或 br。**每个连接单独一行，不要用 & 号连接多个节点**）：
```mermaid
flowchart LR
  A[核心概念] --> B[子方向1]
  A --> C[子方向2]
  B --> D[技术方法1]
  C --> E[技术方法2]
```

{data}"""}
    ])
    # 清理 AI 在 Mermaid 代码块中混入的 HTML 标签和非法语法
    report_clean = re.sub(r'<[^>]+>', '', report)
    report_clean = re.sub(r'(\w+)\s*&', '', report_clean)  # 去掉 X & Y --> Z 中的 &
    steps.append(("Step4-报告", {"len": len(report_clean)}))
    return report_clean, steps


def lab_insight(user_input):
    """项目洞悉：一个仓库的综合全息分析"""
    steps = []
    parts = user_input.replace(" ","").split("/")
    if len(parts) < 2: return "请提供 owner/repo 格式", []
    o, r = parts[0], parts[1]
    url_s = f"https://www.gitlink.org.cn/{o}/{r}"

    info = run(f'gitlink-cli repo +info --owner {o} --repo {r} --format json')
    prs = run(f'gitlink-cli pr +list --owner {o} --repo {r} --format json')
    issues = run(f'gitlink-cli issue +list --owner {o} --repo {r} --format json')
    steps.append(("Step1-数据采集", {}))

    # 提取贡献者
    authors = set()
    try:
        for i in json.loads(prs).get("data",{}).get("issues",[]):
            if i.get("author_login"): authors.add(i["author_login"])
    except: pass
    user_d = []
    for a in list(authors)[:5]:
        u = run(f'gitlink-cli user +info --login {a} --format json')
        user_d.append(f"# {a}\n{u}")

    data = f"# [{o}/{r}]({url_s})\n{info}\n\n# PR\n{prs}\n\n# Issues\n{issues}\n\n" + "\n".join(user_d)
    report = llm([
        {"role": "system", "content": f"你是一个项目洞悉分析师。当前日期{NOW}。综合仓库数据生成全息分析报告。"},
        {"role": "user", "content": f"""仓库: [{o}/{r}]({url_s})
贡献者: {', '.join(authors) if authors else '无'}

请综合以下数据生成项目洞悉报告，包含：
1. 项目概况（语言、规模、描述）
2. 社区活跃度（贡献者、PR、Issue）
3. 团队画像（核心贡献者特点）
4. 综合健康度评估与建议
所有仓库名用超链接 [owner/repo](https://www.gitlink.org.cn/owner/repo)。

{data}"""}
    ])
    steps.append(("Step2-报告", {"len": len(report)}))
    return report, steps


def lab_compliance(user_input):
    """合规复现检查：License、README、CI、Release"""
    steps = []
    parts = user_input.replace(" ","").split("/")
    if len(parts) < 2: return "请提供 owner/repo 格式", []
    o, r = parts[0], parts[1]
    url_s = f"https://www.gitlink.org.cn/{o}/{r}"

    info = run(f'gitlink-cli repo +info --owner {o} --repo {r} --format json')
    builds = run(f'gitlink-cli ci +builds --owner {o} --repo {r} --format json')
    steps.append(("Step1-数据采集", {}))

    # 提取关键字段
    has_license, has_readme, has_ci, size, desc, release = "?", "?", "?", "?", "?", 0
    try:
        d = json.loads(info).get("data",{})
        has_license = "✅ 有" if d.get("license_id") else "❌ 无"
        has_readme = "✅ 有" if d.get("description") else "⚠️ 可能无"
        has_ci = "✅ 已激活" if d.get("open_devops") else "❌ 未激活"
        size = d.get("size","?")
        desc = (d.get("description") or "无描述")[:100]
        release = d.get("version_releases_count",0)
    except: pass

    data = f"# [{o}/{r}]({url_s})\nLicense: {has_license}\nCI: {has_ci}\nSize: {size}\nRelease: {release}\nDesc: {desc}\n{info}\n\n# CI Builds\n{builds}"
    report = llm([
        {"role": "system", "content": f"你是一个开源合规分析师。当前日期{NOW}。检查仓库的合规性和可复现性。"},
        {"role": "user", "content": f"""仓库: [{o}/{r}]({url_s})

检查结果：
- License: {has_license}
- CI激活: {has_ci}
- Release: {release} 个
- 描述: {desc}

请在此基础上生成合规检查报告：
1. License 合规性（是否有许可证、是否开源友好）
2. 文档完整性（README、描述）
3. CI/CD 完善度（是否激活、构建历史）
4. 可复现性（Release、依赖管理）
5. 综合评分（满分 20）和改进建议

{data}"""}
    ])
    steps.append(("Step2-报告", {"len": len(report)}))
    return report, steps


def lab_match(user_input):
    """协作匹配：找入门 Issue + 评估社区友好度"""
    steps = []
    parts = user_input.replace(" ","").split("/")
    if len(parts) < 2: return "请提供 owner/repo 格式", []
    o, r = parts[0], parts[1]
    url_s = f"https://www.gitlink.org.cn/{o}/{r}"

    info = run(f'gitlink-cli repo +info --owner {o} --repo {r} --format json')
    prs = run(f'gitlink-cli pr +list --owner {o} --repo {r} --format json')
    issues = run(f'gitlink-cli issue +list --owner {o} --repo {r} --state open --format json')
    steps.append(("Step1-数据采集", {}))

    data = f"# [{o}/{r}]({url_s})\n{info}\n\n# PR\n{prs}\n\n# Open Issues\n{issues}"
    report = llm([
        {"role": "system", "content": f"你是一个开源协作匹配专家。当前日期{NOW}。评估项目对新贡献者的友好度。"},
        {"role": "user", "content": f"""仓库: [{o}/{r}]({url_s})

请生成协作匹配报告：
1. 项目概览（技术栈、社区规模）
2. 入门友好度分析：
   - 是否有 good-first-issue 标签
   - Issue 描述是否清晰
   - PR Review 是否及时
3. 推荐适合贡献的方向（具体 Issue 或模块）
4. 社区健康度（贡献者多样性、响应速度）
仓库名用超链接。

{data}"""}
    ])
    steps.append(("Step2-报告", {"len": len(report)}))
    return report, steps


def lab_track(user_input):
    """进度跟踪与预警：监控多个仓库的活动状态"""
    steps = []
    repos = [r.strip().replace(" ","") for r in user_input.split(",") if r.strip()]
    if not repos: return "请提供仓库列表，用逗号分隔", []

    items = []
    warns = {"stale": [], "no_ci": [], "inactive": []}
    for repo in repos:
        if "/" not in repo: continue
        o, rn = repo.split("/")[:2]
        info = run(f'gitlink-cli repo +info --owner {o} --repo {rn} --format json')
        try:
            d = json.loads(info).get("data",{})
            contrib = d.get("contributor_users_count",0)
            ci = d.get("open_devops",False)
            updated = d.get("full_name","?")
            items.append({"repo": repo, "contrib": contrib, "ci": ci, "data": d})
            if not ci: warns["no_ci"].append(repo)
            if contrib == 0: warns["inactive"].append(repo)
        except: pass

    steps.append(("Step1-巡检", {"count": len(items), "warns": {k: len(v) for k,v in warns.items()}}))

    def repo_info_line(repo):
        o, rn = repo.split("/")[:2]
        return f"# {repo}\n{run(f'gitlink-cli repo +info --owner {o} --repo {rn} --format json')}"
    data_lines = [repo_info_line(r) for r in repos if "/" in r]
    data = "\n\n".join(data_lines)
    warn_info = "\n".join([f"- ⚠️ {r}: {'CI未激活' if r in warns['no_ci'] else ''} {'无活跃贡献者' if r in warns['inactive'] else ''}" for r in repos if r in warns['no_ci'] or r in warns['inactive']]) or "无预警"
    report = llm([
        {"role": "system", "content": f"你是一个开源项目进度跟踪分析师。当前日期{NOW}。生成多仓库进度报告和预警。"},
        {"role": "user", "content": f"""监控仓库: {', '.join(repos)}
预警信息: {warn_info}

请生成进度跟踪报告：
1. 各仓库状态概览（健康/警告/危险）
2. 详细状态表（贡献者、CI、活跃度）
3. 预警详情（哪些仓库需要关注）
4. 整体健康度评估

{data}"""}
    ])
    steps.append(("Step3-报告", {"len": len(report)}))
    return report, steps


LAB_AGENTS = {
    "lab-hotspot": lab_hotspot,
    "lab-insight": lab_insight,
    "lab-compliance": lab_compliance,
    "lab-match": lab_match,
    "lab-track": lab_track,
}

AGENTS = {
    "research-tracker": agent_research,
    "contributor-insight": agent_contributor,
    "issue-triage": agent_issue,
    "ci-health": agent_ci,
    "repo-health": agent_repo_health,
    "pr-analytics": agent_pr_analytics,
    "cross-search": agent_cross_search,
    "user-analysis": agent_user_analysis,
    "repo-compare": agent_repo_compare,
    **LAB_AGENTS,
}


# ── Routes ──

@app.route("/")
def index():
    return render_template("index.html", skills=SKILL_INFO, url_map={v: k for k, v in SKILL_NAMES.items()})


@app.route("/<slug>")
def page(slug):
    name = SKILL_NAMES.get(slug, slug)
    info = SKILL_INFO.get(name)
    if not info:
        return "Skill not found", 404
    return render_template("skill.html", skill_name=name, info=info)


@app.route("/api/run", methods=["POST"])
def api_run():
    name = request.form.get("skill", "")
    user_input = request.form.get("input", "").strip()
    if not name or not user_input:
        return jsonify({"error": "缺少参数"}), 400

    agent = AGENTS.get(name)
    if not agent:
        return jsonify({"error": f"未知 skill: {name}"}), 400

    try:
        report, steps = agent(user_input)
    except Exception as e:
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    (HISTORY_DIR / f"{name}_{timestamp}.md").write_text(
        f"# {SKILL_INFO[name]['title']} 报告\n\n## 输入\n{user_input}\n\n## 结果\n\n{report}\n\n---\n*生成: {time.strftime('%Y-%m-%d %H:%M:%S')}*",
        encoding="utf-8"
    )
    return jsonify({"report": report, "steps": steps})


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=int(os.environ.get("PORT", 5000)))
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--debug", action="store_true", default=False)
    args = p.parse_args()
    print(f"GitLink Skills Web Service: http://{args.host}:{args.port}")
    app.run(host=args.host, port=args.port, debug=args.debug)
