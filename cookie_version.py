#!/usr/bin/env python3    # -*- coding: utf-8 -*
"""
SUSTech-Grade-Fetcher
cookie_version.py 南科大 TIS 成绩查询脚本（手动填 Cookie 版：支持本科生与研究生）
适用场景：CAS 登录触发验证码/二次认证，脚本无法自动登录
@author: Heimao-c
@date: 2026-02-26
"""

import urllib3
import requests

urllib3.disable_warnings()

# ================== 用户配置区 ==================
# 请在此处填写从浏览器抓取的 Cookie
TIS_ROUTE = "填这里"
TIS_JSESSIONID = "填这里"
# ================================================

BASE = "https://tis.sustech.edu.cn"

# 默认参数（本科生）
ROLE_CODE = "01"
GO_URL = f"{BASE}/cjgl/grcjcx/go/1"
QXDM = "00208"
PYLX = "1"

PDSC_URL = f"{BASE}/component/pdsc"
GRADE_URL = f"{BASE}/cjgl/grcjcx/grcjcx"
XSZD_URL = f"{BASE}/cjgl/grcjcx/xszd"
GPA_URL = f"{BASE}/cjgl/grcjcx/getgpa"

def set_identity():
    global ROLE_CODE, GO_URL, QXDM, PYLX
    print("==============================")
    print("南科大 TIS 成绩查询工具 (Cookie版)")
    print("1. 本科生")
    print("2. 研究生")
    print("==============================")
    choice = input("请选择您的身份 (1或2) [默认1]: ").strip()
    if choice == "2":
        ROLE_CODE = "02"
        GO_URL = f"{BASE}/cjgl/grcjcx/go/2"
        QXDM = "00315"
        PYLX = "2"

def build_session(route, jsessionid):
    s = requests.Session()
    s.verify = False
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "X-Requested-With": "XMLHttpRequest"
    })
    s.cookies.set("route", route, domain="tis.sustech.edu.cn", path="/")
    s.cookies.set("JSESSIONID", jsessionid, domain="tis.sustech.edu.cn", path="/")
    return s

def open_grade_page_and_set_role(s):
    s.get(GO_URL, headers={"Upgrade-Insecure-Requests": "1"}, timeout=15)
    s.post(PDSC_URL, headers={"Content-Type": "application/x-www-form-urlencoded"}, data=f"qxdm={QXDM}&jsdm={ROLE_CODE}", timeout=15)

def fetch_data(s):
    # 模拟真实访问流程
    s.post(XSZD_URL, headers={"RoleCode": ROLE_CODE}, timeout=15)
    gpa_resp = s.post(GPA_URL, headers={"RoleCode": ROLE_CODE}, timeout=15).json()
    
    all_rows = []
    current = 1
    while True:
        r = s.post(
            GRADE_URL, 
            headers={"Content-Type": "application/json", "RoleCode": ROLE_CODE}, 
            json={"xn": None, "xq": None, "cxbj": "-1", "pylx": PYLX, "current": current, "pageSize": 100}, 
            timeout=15
        )
        data = r.json()
        content = data.get("content", {})
        lst = content.get("list", [])
        all_rows.extend(lst)
        
        if content.get("isLastPage") is True or content.get("hasNextPage") is False or not lst:
            break
        current += 1
        
    return gpa_resp, all_rows

def _wcswidth(s: str) -> int:
    s = "" if s is None else str(s)
    return sum(2 if ord(ch) > 127 else 1 for ch in s)

def _pad(s: str, width: int) -> str:
    s = "" if s is None else str(s)
    return s + (" " * max(0, width - _wcswidth(s)))

def print_summary(gpa: dict):
    g = gpa.get("GPA", "-")
    pm = gpa.get("PM", "-")
    zrs = gpa.get("ZRS", "-")
    hdxf = gpa.get("HDXF", "-")
    tgkc = gpa.get("TGKC", "-")
    pmfw = gpa.get("PM_FW", gpa.get("BL", "-"))

    print("\nGPA 概览")
    print(f"  GPA: {g}    排名: {pm}/{zrs}    排名范围(%): {pmfw}")
    print(f"  获得学分: {hdxf}    通过课程数: {tgkc}")
    print()

def print_grades_table(rows: list):
    if not rows:
        print("（没有查到成绩）")
        return

    rows = sorted(rows, key=lambda r: (r.get("xnxq") or "", r.get("kcdm") or "", r.get("kcmc") or ""))

    lines_by_sem = {}
    for r in rows:
        sem = r.get("xnxqmc") or r.get("xnxq") or "未知学期"
        course = f"{r.get('kcdm') or '-'} {r.get('kcmc') or '-'}"
        xf = "-" if r.get("xf") is None else str(r.get("xf"))
        zpcj = r.get("zpcj") or r.get("xszscj") or "-"
        xscj = r.get("xscj") or "-"
        pm_, zrs_ = r.get("pm"), r.get("zrs")
        rank = f"{pm_}/{zrs_}" if pm_ and zrs_ else "-"
        khfs = r.get("khfs") or "-"
        kcxz = r.get("kcxz") or "-"

        lines_by_sem.setdefault(sem, []).append({
            "课程": course,
            "学分": xf,
            "总评": str(zpcj),
            "等级": str(xscj),
            "排名": rank,
            "考核": khfs,
            "性质": kcxz,
        })

    cols = ["课程", "学分", "总评", "等级", "排名", "考核", "性质"]
    colw = {c: _wcswidth(c) for c in cols}
    for ls in lines_by_sem.values():
        for row in ls:
            for c in cols:
                colw[c] = max(colw[c], _wcswidth(row.get(c, "")))

    def sep(ch="─", mid="┼"):
        return mid.join(ch * (colw[c] + 2) for c in cols)

    top = "┌" + sep("─", "┬") + "┐"
    mid = "├" + sep("─", "┼") + "┤"
    bot = "└" + sep("─", "┴") + "┘"
    header = "│" + "│".join(f" {_pad(c, colw[c])} " for c in cols) + "│"

    total = sum(len(v) for v in lines_by_sem.values())
    print(f"共 {total} 条成绩\n")

    for sem in sorted(lines_by_sem.keys()):
        print(f"【{sem}】")
        print(top)
        print(header)
        print(mid)
        for row in lines_by_sem[sem]:
            line = "│" + "│".join(f" {_pad(row[c], colw[c])} " for c in cols) + "│"
            print(line)
        print(bot)
        print()

def main():
    if "填这里" in (TIS_ROUTE, TIS_JSESSIONID):
        print("✗ 请先用代码编辑器打开 cookie_version.py 并在最前方填写 TIS_ROUTE 和 TIS_JSESSIONID")
        print("  获取方法：浏览器登录 TIS -> 开发者工具 Network -> 任选一个 tis 请求 -> Headers -> Cookie")
        return
        
    set_identity()
    print("[\x1b[0;32m+\x1b[0m] 已读取 Cookie，拉取数据中...")
    s = build_session(TIS_ROUTE, TIS_JSESSIONID)
    open_grade_page_and_set_role(s)
    gpa, rows = fetch_data(s)
    
    print_summary(gpa)
    print_grades_table(rows)

if __name__ == "__main__":
    main()