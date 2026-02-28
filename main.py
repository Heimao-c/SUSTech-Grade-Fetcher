#!/usr/bin/env python3    # -*- coding: utf-8 -*
"""
SUSTech-Grade-Fetcher
main.py 南科大 TIS 成绩查询脚本（自动登录版：支持本科生与研究生）
@author: Heimao-c
@date: 2026-02-26
"""

import urllib3
import requests
import getpass
from re import findall

urllib3.disable_warnings()

BASE = "https://tis.sustech.edu.cn"
CAS_LOGIN_URL = "https://cas.sustech.edu.cn/cas/login?service=https%3A%2F%2Ftis.sustech.edu.cn%2Fcas"

# 根据身份动态赋值的全局变量
ROLE_CODE = "01"
GO_URL = f"{BASE}/cjgl/grcjcx/go/1"
QXDM = "00208"
PYLX = "1"

PDSC_URL = f"{BASE}/component/pdsc"
GRADE_URL = f"{BASE}/cjgl/grcjcx/grcjcx"
XSZD_URL = f"{BASE}/cjgl/grcjcx/xszd"
GPA_URL = f"{BASE}/cjgl/grcjcx/getgpa"

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36"

HEAD_BASE = {
    "user-agent": UA,
    "x-requested-with": "XMLHttpRequest",
    "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
    "connection": "keep-alive",
}

def set_identity():
    global ROLE_CODE, GO_URL, QXDM, PYLX
    print("==============================")
    print("南科大 TIS 成绩查询工具")
    print("1. 本科生")
    print("2. 研究生")
    print("==============================")
    choice = input("请选择您的身份 (1或2) [默认1]: ").strip()
    
    if choice == "2":
        ROLE_CODE = "02"
        GO_URL = f"{BASE}/cjgl/grcjcx/go/2"
        QXDM = "00315"
        PYLX = "2"
    else:
        ROLE_CODE = "01"
        GO_URL = f"{BASE}/cjgl/grcjcx/go/1"
        QXDM = "00208"
        PYLX = "1"

def cas_login(user_name: str, pwd: str):
    print("[\x1b[0;36m!\x1b[0m] 测试CAS链接...")
    try:
        r0 = requests.get(CAS_LOGIN_URL, headers=HEAD_BASE, verify=False, timeout=10)
        r0.raise_for_status()
        print("[\x1b[0;32m+\x1b[0m] 成功连接到CAS...")
    except Exception as e:
        print(f"[\x1b[0;31mx\x1b[0m] 不能访问CAS: {e}")
        return "", ""

    try:
        execution = str(r0.text).split('name="execution" value="')[1].split('"')[0]
    except Exception:
        print("[\x1b[0;31mx\x1b[0m] 解析 CAS execution 失败（页面结构可能变化）")
        return "", ""

    print("[\x1b[0;36m!\x1b[0m] 登录中...")
    data = {"username": user_name, "password": pwd, "execution": execution, "_eventId": "submit"}
    r1 = requests.post(CAS_LOGIN_URL, data=data, allow_redirects=False, headers=HEAD_BASE, verify=False, timeout=10)

    if "Location" not in r1.headers:
        print("[\x1b[0;31mx\x1b[0m] 登录失败：可能是用户名/密码错误，或触发验证码/二次认证")
        return "", ""

    print("[\x1b[0;32m+\x1b[0m] 登录成功，跳转 TIS...")
    r2 = requests.get(r1.headers["Location"], allow_redirects=False, headers=HEAD_BASE, verify=False, timeout=10)
    set_cookie = r2.headers.get("Set-Cookie", "")
    try:
        route_ = findall(r"route=(.+?);", set_cookie)[0]
        jsessionid = findall(r"JSESSIONID=(.+?);", set_cookie)[0]
    except Exception:
        print("[\x1b[0;31mx\x1b[0m] 解析 TIS cookie 失败")
        return "", ""

    return route_, jsessionid

def build_session(route: str, jsessionid: str) -> requests.Session:
    s = requests.Session()
    s.verify = False
    s.headers.update({"User-Agent": UA, "Accept-Language": HEAD_BASE["accept-language"], "Connection": "keep-alive"})
    s.cookies.set("route", route, domain="tis.sustech.edu.cn", path="/")
    s.cookies.set("JSESSIONID", jsessionid, domain="tis.sustech.edu.cn", path="/")
    return s

def open_grade_page_and_set_role(s: requests.Session):
    r1 = s.get(GO_URL, headers={"Referer": f"{BASE}/authentication/main", "Upgrade-Insecure-Requests": "1"}, timeout=15, allow_redirects=True)
    if r1.status_code != 200:
        raise RuntimeError(f"go 接口访问失败")

    r2 = s.post(PDSC_URL, headers={"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8", "X-Requested-With": "XMLHttpRequest"}, data=f"qxdm={QXDM}&jsdm={ROLE_CODE}", timeout=15)
    if r2.status_code != 200:
        raise RuntimeError(f"pdsc 设置角色失败")

def fetch_xszd(s: requests.Session):
    s.post(XSZD_URL, headers={"Origin": BASE, "Referer": GO_URL, "RoleCode": ROLE_CODE, "X-Requested-With": "XMLHttpRequest"}, timeout=15)

def fetch_gpa(s: requests.Session) -> dict:
    r = s.post(GPA_URL, headers={"Origin": BASE, "Referer": GO_URL, "RoleCode": ROLE_CODE, "X-Requested-With": "XMLHttpRequest"}, timeout=15)
    return r.json()

def fetch_grades(s: requests.Session, page_size: int = 50) -> list:
    all_rows = []
    current = 1
    base_payload = {"xn": None, "xq": None, "kcmc": None, "cxbj": "-1", "pylx": PYLX, "current": 1, "pageSize": page_size, "sffx": None}

    while True:
        payload = dict(base_payload)
        payload["current"] = current
        r = s.post(GRADE_URL, headers={"Content-Type": "application/json", "Origin": BASE, "Referer": GO_URL, "RoleCode": ROLE_CODE, "X-Requested-With": "XMLHttpRequest"}, json=payload, timeout=15)
        data = r.json()
        content = data.get("content") or {}
        lst = content.get("list") or []
        all_rows.extend(lst)

        if content.get("isLastPage") is True or content.get("hasNextPage") is False or not lst:
            break
        current += 1
    return all_rows

def _wcswidth(s: str) -> int:
    return sum(2 if ord(ch) > 127 else 1 for ch in ("" if s is None else str(s)))

def _pad(s: str, width: int) -> str:
    s = "" if s is None else str(s)
    return s + (" " * max(0, width - _wcswidth(s)))

def print_summary(gpa: dict):
    print("\nGPA 概览")
    print(f"  GPA: {gpa.get('GPA', '-')}    排名: {gpa.get('PM', '-')}/{gpa.get('ZRS', '-')}    排名范围(%): {gpa.get('PM_FW', gpa.get('BL', '-'))}")
    print(f"  获得学分: {gpa.get('HDXF', '-')}    通过课程数: {gpa.get('TGKC', '-')}\n")

def print_grades_table(rows: list):
    if not rows:
        print("（没有查到成绩）")
        return
    rows = sorted(rows, key=lambda r: (r.get("xnxq") or "", r.get("kcdm") or ""))
    lines_by_sem = {}
    for r in rows:
        sem = r.get("xnxqmc") or r.get("xnxq") or "未知学期"
        lines_by_sem.setdefault(sem, []).append({
            "课程": f"{r.get('kcdm') or '-'} {r.get('kcmc') or '-'}",
            "学分": "-" if r.get("xf") is None else str(r.get("xf")),
            "总评": str(r.get("zpcj") or r.get("xszscj") or "-"),
            "等级": str(r.get("xscj") or "-"),
            "排名": f"{r.get('pm')}/{r.get('zrs')}" if r.get("pm") and r.get("zrs") else "-",
            "考核": r.get("khfs") or "-",
            "性质": r.get("kcxz") or "-",
        })
    cols = ["课程", "学分", "总评", "等级", "排名", "考核", "性质"]
    colw = {c: _wcswidth(c) for c in cols}
    for ls in lines_by_sem.values():
        for row in ls:
            for c in cols: colw[c] = max(colw[c], _wcswidth(row.get(c, "")))
    def sep(ch="─", mid="┼"): return mid.join(ch * (colw[c] + 2) for c in cols)
    top, mid, bot = "┌" + sep("─", "┬") + "┐", "├" + sep("─", "┼") + "┤", "└" + sep("─", "┴") + "┘"
    header = "│" + "│".join(f" {_pad(c, colw[c])} " for c in cols) + "│"
    
    print(f"共 {sum(len(v) for v in lines_by_sem.values())} 条成绩\n")
    for sem in sorted(lines_by_sem.keys()):
        print(f"【{sem}】\n{top}\n{header}\n{mid}")
        for row in lines_by_sem[sem]: print("│" + "│".join(f" {_pad(row[c], colw[c])} " for c in cols) + "│")
        print(f"{bot}\n")

def main():
    set_identity()
    
    username = input("请输入学号 (Username): ").strip()
    password = getpass.getpass("请输入密码 (Password 盲打不可见): ")
    
    route, jsid = cas_login(username, password)
    if not route or not jsid:
        return

    print("[\x1b[0;32m+\x1b[0m] 已获取 TIS cookie，拉取数据中...")
    s = build_session(route, jsid)
    open_grade_page_and_set_role(s)
    fetch_xszd(s)
    
    print_summary(fetch_gpa(s))
    print_grades_table(fetch_grades(s, page_size=150))

if __name__ == "__main__":
    main()