#!/usr/bin/env python3
"""GitHub Skills Web Service - 14 modules"""

import os, re, json, subprocess, time, traceback
from flask import Flask, request, jsonify, render_template
import requests

app = Flask(__name__)
NOW = time.strftime("%Y-%m-%d")

ENV = os.environ.copy()
# 通过环境变量 GH_TOKEN 设置 GitHub Token（https://github.com/settings/tokens）
ENV["GH_TOKEN"] = os.environ.get("GH_TOKEN", "")

SKILL_MAP = {
    "research-tracker":{"title":"技术调研","prompt":"研究主题","placeholder":"OpenClaw、大模型、AI Agent","intro":"输入研究主题，自动搜索GitHub相关项目，深度评估后生成调研报告。","output_desc":"热点概览（项目数/语言/活跃度）\n排行榜（星数/链接）\n重点分析\n趋势洞察"},
    "contributor-insight":{"title":"贡献者分析","prompt":"仓库(owner/repo)","placeholder":"openclaw/openclaw","intro":"输入仓库地址，分析贡献者活跃度、团队健康度。","output_desc":"团队概览\n活跃度排行榜（PR数/趋势）\n重点贡献者分析\n健康度评估"},
    "issue-triage":{"title":"Issue分拣","prompt":"仓库(owner/repo)","placeholder":"openclaw/openclaw","intro":"自动分类Issue，评估紧急度、复杂度。","output_desc":"Issue总览\n类型分类（Bug/Feature等）\n紧急度评估\n行动建议"},
    "ci-health":{"title":"CI健康巡检","prompt":"仓库(owner/repo)","placeholder":"facebook/react","intro":"检查CI状态、构建历史、成功率。","output_desc":"健康度总览\n构建趋势\n故障分析"},
    "repo-health":{"title":"仓库健康巡检","prompt":"仓库(owner/repo)","placeholder":"openclaw/openclaw","intro":"综合评估仓库活跃度、社区规模、风险。","output_desc":"基本信息\nPR/Issue健康度\n综合评分与建议"},
    "pr-analytics":{"title":"PR效率分析","prompt":"仓库(owner/repo)","placeholder":"openclaw/openclaw","intro":"统计PR吞吐量、合并率、贡献者。","output_desc":"PR吞吐量\n合并效率\n贡献者排行榜"},
    "cross-search":{"title":"跨维搜索","prompt":"搜索主题","placeholder":"AI Agent","intro":"同时搜索仓库、代码、Issue三维。","output_desc":"各维度命中\n仓库结果\n代码摘要\nIssue热点"},
    "user-analysis":{"title":"用户分析","prompt":"用户名","placeholder":"torvalds","intro":"查看用户信息、活跃度、项目参与。","output_desc":"基本信息\n活跃度分析\n项目贡献"},
    "repo-compare":{"title":"仓库对比","prompt":"AvsB","placeholder":"facebook/react vs vuejs/core","intro":"对比两个仓库的指标差异。","output_desc":"基本信息对比\n社区活跃度对比\n综合结论"},
    "lab-hotspot":{"title":"热点追踪","prompt":"研究主题","placeholder":"大模型","lab":True,"intro":"多关键词搜索GitHub项目，深度评估+领域知识图谱。","output_desc":"热点概览\n排行榜（星数/链接）\n领域知识图谱（Mermaid）\n趋势洞察"},
    "lab-insight":{"title":"项目洞悉","prompt":"仓库(owner/repo)","placeholder":"openclaw/openclaw","lab":True,"intro":"综合仓库信息+贡献者+PR/Issue生成全息分析。","output_desc":"项目概况\n社区活跃度\n团队画像\n健康度评估"},
    "lab-compliance":{"title":"合规检查","prompt":"仓库(owner/repo)","placeholder":"openclaw/openclaw","lab":True,"intro":"检查License/CI/文档完整性。","output_desc":"License合规性\n文档完整性\nCI/CD完善度\n综合评分"},
    "lab-match":{"title":"协作匹配","prompt":"仓库(owner/repo)","placeholder":"openclaw/openclaw","lab":True,"intro":"分析Issue和社区健康度。","output_desc":"入门友好度\n推荐贡献方向\n社区活跃度"},
    "lab-track":{"title":"进度跟踪","prompt":"仓库列表(逗号分隔)","placeholder":"repo1,repo2,repo3","lab":True,"intro":"批量巡检多仓库状态。","output_desc":"各仓库状态概览\n详细指标表\n预警详情"},
}
SKILL_NAMES = {"research":"research-tracker","contributor":"contributor-insight","issue-triage":"issue-triage","ci-health":"ci-health","repo-health":"repo-health","pr-analytics":"pr-analytics","cross-search":"cross-search","user-analysis":"user-analysis","repo-compare":"repo-compare","lab-hotspot":"lab-hotspot","lab-insight":"lab-insight","lab-compliance":"lab-compliance","lab-match":"lab-match","lab-track":"lab-track"}
LAB_FLOW = [
    ("lab-hotspot","热点追踪","多关键词搜索GitHub项目，深度评估+领域知识图谱"),
    ("lab-insight","项目洞悉","综合仓库信息+贡献者+PR/Issue，全息分析"),
    ("lab-compliance","合规检查","检查License/CI/文档完整性，合规评分"),
    ("lab-match","协作匹配","分析Issue和社区健康度，评估入门友好度"),
    ("lab-track","进度跟踪","批量巡检多仓库状态，健康/警告/危险告警"),
]

def run(cmd, timeout=30):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout, env=ENV)
        return r.stdout.strip()[:50000] or r.stderr.strip()[:1000]
    except: return "[err]"

def llm(messages):
    key = os.environ.get("API_KEY") or ""
    try:
        r = requests.post("https://api.deepseek.com/v1/chat/completions",
            headers={"Authorization":"Bearer "+key,"Content-Type":"application/json"},
            json={"model":"deepseek-chat","messages":messages,"max_tokens":8192,"temperature":0.7}, timeout=180)
        d = r.json()
        return d["choices"][0]["message"]["content"] if "choices" in d else str(d)[:300]
    except Exception as e: return str(e)

def gh_repo(repo):
    return run('gh repo view '+repo+' --json name,owner,stargazerCount,description,url 2>/dev/null')

# --- 工具 Agents ---
def a_research(ui):
    s=[]
    q=ui.strip().lower()
    cmd='gh search repos "'+q+'" --limit 15 --sort stars --json fullName,stargazersCount,language,description,url,owner 2>/dev/null'
    raw=run(cmd); allp={}
    try:
        for p in json.loads(raw): allp[p["fullName"]]=p
    except: pass
    s.append(("Search",{"count":len(allp)}))
    top=sorted(allp.values(), key=lambda x:x.get("stargazersCount",0), reverse=True)[:5]
    lines=[]
    for p in top:
        r=p["fullName"]; n=p.get("stargazersCount",0); lang=p.get("language","?") or "?"
        lines.append("- [%s](https://github.com/%s) | %s stars | %s | %s" % (r,r,n,lang,(p.get("description") or "?")[:80]))
    if not lines:
        rd=gh_repo(q)
        if "404" not in rd and rd.strip():
            try:
                rdj=json.loads(rd)
                lines.append("- [%s](https://github.com/%s) | %s stars | %s" % (q,q,rdj.get("stargazerCount","?"),rdj.get("description","")))
            except: pass
    prompt=("当前日期:"+NOW+"\n研究主题:"+ui+"\n\nGitHub真实搜索到的仓库(仅分析以下,禁止编造):\n"+"\n".join(lines)+"\n\n生成中文报告:一、热点概览 二、排行榜(含链接) 三、重点分析 四、趋势洞察")
    report=llm([{"role":"system","content":"GitHub数据分析助手。只分析用户提供的仓库列表，绝不编造任何数据。"},{"role":"user","content":prompt}])
    return report,s

def a_contributor(ui):
    s=[]; p=ui.replace(" ","").split("/"); repo=p[0]+"/"+p[1]
    info=gh_repo(repo)
    prs=run('gh pr list -R '+repo+' --state all --limit 30 --json number,title,state,createdAt,author,url 2>/dev/null')
    s.append(("Data",{}))
    authors=set()
    try:
        for i in json.loads(prs):
            a=i.get("author",{}).get("login")
            if a: authors.add(a)
    except: pass
    ud=[run('gh api users/'+a+' 2>/dev/null') for a in list(authors)[:5] if not "Not Found" in run('gh api users/'+a+' 2>/dev/null')[:50]]
    prompt="Date:"+NOW+"\nRepo:["+repo+"](https://github.com/"+repo+")\nContributors:"+",".join(authors)+"\nReport: overview, rankings, analysis, health\n"+info+"\n"+prs[:3000]
    report=llm([{"role":"system","content":"Chinese contributor report from real GitHub data."},{"role":"user","content":prompt}])
    return report,s

def a_issue(ui):
    s=[]; p=ui.replace(" ","").split("/"); repo=p[0]+"/"+p[1]
    info=gh_repo(repo)
    issues=run('gh issue list -R '+repo+' --state open --limit 20 --json number,title,state,createdAt,labels,url 2>/dev/null')
    s.append(("Data",{}))
    report=llm([{"role":"system","content":"Chinese issue triage report from real data."},{"role":"user","content":"Date:"+NOW+"\nRepo:["+repo+"](https://github.com/"+repo+")\nTriage: overview, categories, actions\n"+info+"\n"+issues[:4000]}])
    return report,s

def a_health(ui):
    s=[]; p=ui.replace(" ","").split("/"); repo=p[0]+"/"+p[1]
    info=gh_repo(repo)
    issues=run('gh issue list -R '+repo+' --state open --limit 5 --json number,title 2>/dev/null')
    prs=run('gh pr list -R '+repo+' --state open --limit 5 --json number,title 2>/dev/null')
    s.append(("Data",{}))
    report=llm([{"role":"system","content":"Chinese health report from real data."},{"role":"user","content":"Date:"+NOW+"\nRepo:["+repo+"](https://github.com/"+repo+")\nHealth: info, activity, PR/Issue health, score\n"+info+"\n"+issues[:1000]+"\n"+prs[:1000]}])
    return report,s

def a_pr(ui):
    s=[]; p=ui.replace(" ","").split("/"); repo=p[0]+"/"+p[1]
    prs=run('gh pr list -R '+repo+' --state all --limit 30 --json number,title,state,createdAt,mergedAt,author 2>/dev/null')
    s.append(("PR",{}))
    report=llm([{"role":"system","content":"Chinese PR report from real data."},{"role":"user","content":"Date:"+NOW+"\nRepo:["+repo+"](https://github.com/"+repo+")\nPR report: throughput, merge rate, contributors\n"+prs[:4000]}])
    return report,s

def a_user(ui):
    s=[]; login=ui.strip()
    info=run('gh api users/'+login+' 2>/dev/null')
    repos=run('gh api users/'+login+'/repos?per_page=5&sort=updated 2>/dev/null')
    s.append(("User",{}))
    report=llm([{"role":"system","content":"Chinese user report from real data."},{"role":"user","content":"Date:"+NOW+"\nUser:"+login+"\nReport: profile, activity, projects\n"+info[:2000]+"\n"+repos[:2000]}])
    return report,s

def a_compare(ui):
    s=[]
    parts=[p.strip() for p in ui.replace("vs"," vs ").split("vs") if p.strip()]
    if len(parts)<2: return "Use A vs B format",[]
    a,b=parts[0],parts[1]
    ia=gh_repo(a); ib=gh_repo(b)
    report=llm([{"role":"system","content":"Chinese comparison report from real data."},{"role":"user","content":"Date:"+NOW+"\nA:["+a+"](https://github.com/"+a+")\nB:["+b+"](https://github.com/"+b+")\nComparison\n"+ia+"\n"+ib}])
    return report,s

# --- Lab Agents ---
def lab_hotspot(ui):
    s=[]
    kw_resp=llm([{"role":"user","content":"For "+ui+" give 3-5 search keywords, one per line"}])
    kws=[l.strip("-* ") for l in kw_resp.split("\n") if l.strip()][:5]
    s.append(("KWs",{"kws":kws}))
    allp={}
    for kw in kws:
        for p in json.loads(run('gh search repos "'+kw+'" --limit 10 --sort stars --json fullName,stargazersCount,language,description,url 2>/dev/null') or "[]"):
            k=p.get("fullName","")
            if k: allp[k]=p
    s.append(("Search",{"unique":len(allp)}))
    top=sorted(allp.values(), key=lambda x:x.get("stargazersCount",0), reverse=True)[:8]
    deep=[]
    for p in top:
        r=p["fullName"]; rd=gh_repo(r)
        deep.append("[%s](https://github.com/%s) | stars:%s" % (r,r,p.get("stargazersCount",0)))
        if "404" not in rd:
            deep[-1] += "\n"+rd[:500]
    mermaid_instruction='Also create a Mermaid knowledge graph showing domain concepts. Format:\n```mermaid\nflowchart LR\n  A[Concept] --> B[Sub-field]\n```\nNo HTML tags, no & in connections.'
    prompt="Date:"+NOW+"\nTopic:"+ui+"\nKeywords:"+",".join(kws)+"\n\nReal repos:\n"+"\n".join(deep)+"\n\nGenerate Chinese report: overview, rankings(with links), analysis, trends. "+mermaid_instruction
    report=llm([{"role":"system","content":"Research analyst. ONLY use repos listed. Generate Chinese report with Mermaid knowledge graph."},{"role":"user","content":prompt}])
    report=re.sub(r'<[^>]+>','',report)
    return report,s

def lab_insight(ui):
    s=[]; p=ui.replace(" ","").split("/"); repo=p[0]+"/"+p[1]
    info=gh_repo(repo)
    prs=run('gh pr list -R '+repo+' --state all --limit 20 --json number,title,state,createdAt,author 2>/dev/null')
    issues=run('gh issue list -R '+repo+' --state open --limit 10 --json number,title,createdAt 2>/dev/null')
    authors=set()
    try:
        for i in json.loads(prs):
            a=i.get("author",{}).get("login")
            if a: authors.add(a)
    except: pass
    ud=[run('gh api users/'+a+' 2>/dev/null')[:800] for a in list(authors)[:3]]
    s.append(("Data",{}))
    prompt="Date:"+NOW+"\nRepo:["+repo+"](https://github.com/"+repo+")\nContributors:"+",".join(authors)+"\n\nInfo:\n"+info+"\n\nPRs:\n"+prs[:2000]+"\n\nIssues:\n"+issues[:2000]+"\n\n"+"\n".join(ud)+"\n\nGenerate Chinese comprehensive insight report."
    report=llm([{"role":"system","content":"Chinese insight report from real data."},{"role":"user","content":prompt}])
    return report,s

def lab_compliance(ui):
    s=[]; p=ui.replace(" ","").split("/"); repo=p[0]+"/"+p[1]
    info=gh_repo(repo)
    # Extract key fields from repo info
    has_license="?"
    try:
        d=json.loads(info)
        if d.get("licenseInfo"): has_license="Yes"
        else: has_license="No"
    except: pass
    s.append(("Data",{}))
    prompt="Date:"+NOW+"\nRepo:["+repo+"](https://github.com/"+repo+")\nLicense:"+has_license+"\n\n"+info+"\n\nGenerate Chinese compliance report: license, docs, CI/CD, reproducibility, score."
    report=llm([{"role":"system","content":"Chinese compliance report from real data."},{"role":"user","content":prompt}])
    return report,s

def lab_match(ui):
    s=[]; p=ui.replace(" ","").split("/"); repo=p[0]+"/"+p[1]
    info=gh_repo(repo)
    issues=run('gh issue list -R '+repo+' --state open --limit 15 --json number,title,labels,url 2>/dev/null')
    prs=run('gh pr list -R '+repo+' --state open --limit 10 --json number,title,author 2>/dev/null')
    s.append(("Data",{}))
    prompt="Date:"+NOW+"\nRepo:["+repo+"](https://github.com/"+repo+")\n\n"+info+"\n\nIssues:\n"+issues[:3000]+"\n\nOpen PRs:\n"+prs[:1000]+"\n\nGenerate Chinese collaboration match report: beginner-friendliness, good-first-issues, community health."
    report=llm([{"role":"system","content":"Chinese collaboration match report from real data."},{"role":"user","content":prompt}])
    return report,s

def lab_track(ui):
    s=[]
    repos=[r.strip().replace(" ","") for r in ui.split(",") if r.strip() and "/" in r]
    if not repos: return "Please provide repo list, comma separated",[]
    data_parts=[]
    warns=[]
    for repo in repos:
        info=gh_repo(repo)
        data_parts.append("# "+repo+"\n"+info[:800])
        try:
            d=json.loads(info)
            if not d.get("stargazerCount"): warns.append(repo+" (no stars)")
        except: pass
    s.append(("Tracked",{"count":len(repos)}))
    prompt="Date:"+NOW+"\nRepos:\n"+"\n".join(data_parts)+"\n\nWarnings:\n"+"\n".join(warns)+"\n\nGenerate Chinese tracking report: status table, warnings, health assessment."
    report=llm([{"role":"system","content":"Chinese progress tracking report from real data."},{"role":"user","content":prompt}])
    return report,s

AGENTS={
    "research-tracker":a_research,"contributor-insight":a_contributor,"issue-triage":a_issue,
    "ci-health":a_health,"repo-health":a_health,"pr-analytics":a_pr,
    "cross-search":a_research,"user-analysis":a_user,"repo-compare":a_compare,
    "lab-hotspot":lab_hotspot,"lab-insight":lab_insight,"lab-compliance":lab_compliance,
    "lab-match":lab_match,"lab-track":lab_track,
}

@app.route("/")
def index():
    return render_template("index.html",skills=SKILL_MAP,
        url_map={v:k for k,v in SKILL_NAMES.items()},
        lab_flow=LAB_FLOW)

@app.route("/<slug>")
def page(slug):
    name=SKILL_NAMES.get(slug,slug)
    info=SKILL_MAP.get(name)
    if not info: return "Skill not found",404
    return render_template("skill.html",skill_name=name,info=info)

@app.route("/api/run",methods=["POST"])
def api_run():
    name=request.form.get("skill",""); ui=request.form.get("input","").strip()
    if not name or not ui: return jsonify({"error":"missing params"}),400
    agent=AGENTS.get(name)
    if not agent: return jsonify({"error":"unknown skill"}),400
    try:
        report,steps=agent(ui)
        report=re.sub(r'<[^>]+>','',report)
    except Exception as e:
        return jsonify({"error":str(e)}),500
    return jsonify({"report":report,"steps":steps})

if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("--port",type=int,default=int(os.environ.get("PORT",5000)))
    p.add_argument("--host",default="0.0.0.0")
    args=p.parse_args()
    print("GitHub Skills: http://"+args.host+":"+str(args.port))
    app.run(host=args.host,port=args.port,debug=False)
