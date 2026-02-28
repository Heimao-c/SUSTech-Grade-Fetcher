// SUSTech-Grade-Fetcher/main.go
// SUSTech TIS 成绩查询工具 (自动识别版)
// 作者: Heimao-c & Gemini
// 日期: 2026.2.26
package main

import (
	"bufio"
	"crypto/tls"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/http/cookiejar"
	"net/url"
	"os"
	"sort"
	"strings"
	"syscall"
	"time"

	"golang.org/x/term"
)

// ================== 全局动态变量 ==================
var (
	RoleCode string
	GoURL    string
	Qxdm     string
	Pylx     string
)

const (
	BaseURL     = "https://tis.sustech.edu.cn"
	CasLoginURL = "https://cas.sustech.edu.cn/cas/login?service=https%3A%2F%2Ftis.sustech.edu.cn%2Fcas"
	PdscURL     = BaseURL + "/component/pdsc"
	GradeURL    = BaseURL + "/cjgl/grcjcx/grcjcx"
	XszdURL     = BaseURL + "/cjgl/grcjcx/xszd"
	GpaURL      = BaseURL + "/cjgl/grcjcx/getgpa"
	UserAgent   = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

// ================== JSON 结构体定义 ==================
type ResponseData struct {
	Code    int             `json:"code"`
	Msg     string          `json:"msg"`
	MsgEn   string          `json:"msg_en"`
	Content json.RawMessage `json:"content"`
}

type GradeContent struct {
	List        []GradeItem `json:"list"`
	Total       int         `json:"total"`
	Pages       int         `json:"pages"`
	Current     int         `json:"current"`
	HasNextPage bool        `json:"hasNextPage"`
	IsLastPage  bool        `json:"isLastPage"`
}

type GradeItem struct {
	Xnxq   string      `json:"xnxq"`
	Xnxqmc string      `json:"xnxqmc"`
	Kcdm   string      `json:"kcdm"`
	Kcmc   string      `json:"kcmc"`
	Xf     interface{} `json:"xf"`
	Zpcj   string      `json:"zpcj"`
	Xszscj string      `json:"xszscj"`
	Xscj   string      `json:"xscj"`
	Pm     interface{} `json:"pm"`
	Zrs    interface{} `json:"zrs"`
	Khfs   string      `json:"khfs"`
	Kcxz   string      `json:"kcxz"`
}

var client *http.Client

func init() {
	jar, _ := cookiejar.New(nil)
	tr := &http.Transport{
		TLSClientConfig: &tls.Config{InsecureSkipVerify: true},
	}
	client = &http.Client{
		Jar:       jar,
		Transport: tr,
		Timeout:   15 * time.Second,
	}
}

func main() {
	defer func() {
		if r := recover(); r != nil {
			fmt.Printf("[\x1b[0;31mx\x1b[0m] 发生严重错误: %v\n", r)
			pauseExit()
		}
	}()

	fmt.Println("==============================")
	fmt.Println("SUSTech TIS 成绩查询工具 (Go)")
	fmt.Println("==============================")
	fmt.Println("1. 本科生")
	fmt.Println("2. 研究生")
	fmt.Print("请选择身份 (1或2) [默认1]: ")

	reader := bufio.NewReader(os.Stdin)
	choice, _ := reader.ReadString('\n')
	choice = strings.TrimSpace(choice)

	if choice == "2" {
		RoleCode = "02"
		GoURL = BaseURL + "/cjgl/grcjcx/go/2"
		Qxdm = "00315"
		Pylx = "2"
	} else {
		RoleCode = "01"
		GoURL = BaseURL + "/cjgl/grcjcx/go/1"
		Qxdm = "00208"
		Pylx = "1"
	}

	username, password := getCredentials(reader)
	if username == "" || password == "" {
		fmt.Println("账号或密码不能为空。")
		pauseExit()
		return
	}

	if err := casLogin(username, password); err != nil {
		fmt.Printf("[\x1b[0;31mx\x1b[0m] 登录失败: %v\n", err)
		pauseExit()
		return
	}

	if err := initTisModule(); err != nil {
		fmt.Printf("[\x1b[0;31mx\x1b[0m] 初始化模块失败: %v\n", err)
		pauseExit()
		return
	}

	fetchXszd()

	gpaData, err := fetchGpa()
	if err != nil {
		fmt.Printf("[\x1b[0;33m-\x1b[0m] 获取GPA出错: %v\n", err)
	} else {
		printGpaSummary(gpaData)
	}

	fmt.Println("正在拉取成绩单...")
	grades, err := fetchAllGrades(150)
	if err != nil {
		fmt.Printf("[\x1b[0;31mx\x1b[0m] 获取成绩列表失败: %v\n", err)
	} else {
		printGradesTable(grades)
	}

	pauseExit()
}

func getCredentials(reader *bufio.Reader) (string, string) {
	fmt.Print("请输入学号 (Username): ")
	username, _ := reader.ReadString('\n')
	
	fmt.Print("请输入密码 (Password 盲打不可见): ")
	bytePassword, err := term.ReadPassword(int(syscall.Stdin))
	if err != nil {
		fmt.Println("\n读取密码失败，回退到明文...")
		password, _ := reader.ReadString('\n')
		return strings.TrimSpace(username), strings.TrimSpace(password)
	}
	fmt.Println()
	return strings.TrimSpace(username), string(bytePassword)
}

func casLogin(username, password string) error {
	fmt.Println("[\x1b[0;36m!\x1b[0m] 正在连接 CAS...")
	req, _ := http.NewRequest("GET", CasLoginURL, nil)
	setHeader(req)
	resp, err := client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	bodyBytes, _ := io.ReadAll(resp.Body)

	parts := strings.Split(string(bodyBytes), `name="execution" value="`)
	if len(parts) < 2 {
		return fmt.Errorf("无法解析 execution 参数")
	}
	execution := strings.Split(parts[1], `"`)[0]

	fmt.Println("[\x1b[0;36m!\x1b[0m] 正在提交登录...")
	client.CheckRedirect = func(req *http.Request, via []*http.Request) error {
		return http.ErrUseLastResponse
	}

	data := url.Values{}
	data.Set("username", username)
	data.Set("password", password)
	data.Set("execution", execution)
	data.Set("_eventId", "submit")

	req, _ = http.NewRequest("POST", CasLoginURL, strings.NewReader(data.Encode()))
	setHeader(req)
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")

	resp, err = client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	client.CheckRedirect = nil

	location := resp.Header.Get("Location")
	if location == "" {
		return fmt.Errorf("登录失败，可能是密码错误或触发了验证码")
	}

	fmt.Println("[\x1b[0;32m+\x1b[0m] 登录成功，跳转 TIS...")
	req, _ = http.NewRequest("GET", location, nil)
	setHeader(req)
	resp, err = client.Do(req)
	if err != nil {
		return fmt.Errorf("跳转 TIS 失败: %v", err)
	}
	defer resp.Body.Close()

	return nil
}

func initTisModule() error {
	req, _ := http.NewRequest("GET", GoURL, nil)
	setHeader(req)
	resp, err := client.Do(req)
	if err != nil || resp.StatusCode != 200 {
		return fmt.Errorf("go访问失败")
	}
	resp.Body.Close()

	data := url.Values{}
	data.Set("qxdm", Qxdm)
	data.Set("jsdm", RoleCode)

	req, _ = http.NewRequest("POST", PdscURL, strings.NewReader(data.Encode()))
	setHeader(req)
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded; charset=UTF-8")
	req.Header.Set("X-Requested-With", "XMLHttpRequest")

	resp, err = client.Do(req)
	if err != nil || resp.StatusCode != 200 {
		return fmt.Errorf("设置角色失败")
	}
	resp.Body.Close()
	return nil
}

func fetchXszd() {
	req, _ := http.NewRequest("POST", XszdURL, nil)
	setApiHeaders(req)
	client.Do(req)
}

func fetchGpa() (map[string]interface{}, error) {
	req, _ := http.NewRequest("POST", GpaURL, nil)
	setApiHeaders(req)

	resp, err := client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	var result map[string]interface{}
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("解析 GPA JSON 失败")
	}
	return result, nil
}

func fetchAllGrades(pageSize int) ([]GradeItem, error) {
	var allRows []GradeItem
	current := 1

	for {
		payload := map[string]interface{}{
			"xn":       nil,
			"xq":       nil,
			"kcmc":     nil,
			"cxbj":     "-1",
			"pylx":     Pylx,
			"current":  current,
			"pageSize": pageSize,
			"sffx":     nil,
		}

		jsonBody, _ := json.Marshal(payload)
		req, _ := http.NewRequest("POST", GradeURL, strings.NewReader(string(jsonBody)))
		setApiHeaders(req)
		req.Header.Set("Content-Type", "application/json")

		resp, err := client.Do(req)
		if err != nil {
			return allRows, err
		}

		var resData ResponseData
		if err := json.NewDecoder(resp.Body).Decode(&resData); err != nil {
			resp.Body.Close()
			return allRows, fmt.Errorf("解析成绩 JSON 失败")
		}
		resp.Body.Close()

		if resData.Code != 200 {
			return allRows, fmt.Errorf("服务器返回错误: %s", resData.Msg)
		}

		var content GradeContent
		if err := json.Unmarshal(resData.Content, &content); err != nil {
			break
		}

		allRows = append(allRows, content.List...)

		if content.IsLastPage || !content.HasNextPage || len(content.List) == 0 {
			break
		}
		if current >= content.Pages {
			break
		}
		current++
	}
	return allRows, nil
}

// ================== 输出美化工具 ==================

func printGpaSummary(gpa map[string]interface{}) {
	getValue := func(key string) string {
		if v, ok := gpa[key]; ok && v != nil {
			return fmt.Sprintf("%v", v)
		}
		return "-"
	}

	fmt.Println("\nGPA 概览")
	fmt.Printf("  GPA: %s    排名: %s/%s    排名范围(%%): %s\n",
		getValue("GPA"), getValue("PM"), getValue("ZRS"),
		getValue("PM_FW"))
	fmt.Printf("  获得学分: %s    通过课程数: %s\n",
		getValue("HDXF"), getValue("TGKC"))
	fmt.Println()
}

func printGradesTable(rows []GradeItem) {
	if len(rows) == 0 {
		fmt.Println("（没有查到成绩）")
		return
	}

	sort.Slice(rows, func(i, j int) bool {
		if rows[i].Xnxq != rows[j].Xnxq {
			return rows[i].Xnxq < rows[j].Xnxq
		}
		return rows[i].Kcdm < rows[j].Kcdm
	})

	grouped := make(map[string][]GradeItem)
	var semesters []string

	for _, r := range rows {
		sem := r.Xnxqmc
		if sem == "" {
			sem = r.Xnxq
		}
		if sem == "" {
			sem = "未知学期"
		}
		if _, exists := grouped[sem]; !exists {
			semesters = append(semesters, sem)
		}
		grouped[sem] = append(grouped[sem], r)
	}

	fmt.Printf("共 %d 条成绩\n", len(rows))
	cols := []string{"课程", "学分", "总评", "等级", "排名", "考核", "性质"}

	for _, sem := range semesters {
		fmt.Printf("\n【%s】\n", sem)
		list := grouped[sem]

		widths := make(map[string]int)
		for _, c := range cols {
			widths[c] = wcwidth(c)
		}

		type PrintRow map[string]string
		var printRows []PrintRow

		for _, item := range list {
			pr := make(PrintRow)
			pr["课程"] = fmt.Sprintf("%s %s", item.Kcdm, item.Kcmc)
			pr["学分"] = fmt.Sprintf("%v", item.Xf)

			zpcj := item.Zpcj
			if zpcj == "" {
				zpcj = item.Xszscj
			}
			if zpcj == "" {
				zpcj = "-"
			}
			pr["总评"] = zpcj

			pr["等级"] = item.Xscj
			if pr["等级"] == "" {
				pr["等级"] = "-"
			}

			if item.Pm != nil && item.Zrs != nil {
				pr["排名"] = fmt.Sprintf("%v/%v", item.Pm, item.Zrs)
			} else {
				pr["排名"] = "-"
			}
			pr["考核"] = item.Khfs
			pr["性质"] = item.Kcxz

			printRows = append(printRows, pr)

			for _, c := range cols {
				w := wcwidth(pr[c])
				if w > widths[c] {
					widths[c] = w
				}
			}
		}

		printLine(cols, widths, "┌", "┬", "┐", "─")
		printRowContent(cols, widths, nil)
		printLine(cols, widths, "├", "┼", "┤", "─")
		for _, pr := range printRows {
			printRowContent(cols, widths, pr)
		}
		printLine(cols, widths, "└", "┴", "┘", "─")
	}
}

func printLine(cols []string, widths map[string]int, left, mid, right, fill string) {
	fmt.Print(left)
	for i, c := range cols {
		fmt.Print(strings.Repeat(fill, widths[c]+2))
		if i < len(cols)-1 {
			fmt.Print(mid)
		}
	}
	fmt.Println(right)
}

func printRowContent(cols []string, widths map[string]int, data map[string]string) {
	fmt.Print("│")
	for _, c := range cols {
		val := c
		if data != nil {
			val = data[c]
		}
		padding := widths[c] - wcwidth(val)
		fmt.Printf(" %s%s │", val, strings.Repeat(" ", padding))
	}
	fmt.Println()
}

func wcwidth(s string) int {
	n := 0
	for _, r := range s {
		if r > 127 {
			n += 2
		} else {
			n += 1
		}
	}
	return n
}

// ================== 通用辅助函数 ==================

func setHeader(req *http.Request) {
	req.Header.Set("User-Agent", UserAgent)
	req.Header.Set("Accept-Language", "zh-CN,zh;q=0.9,en;q=0.8")
	req.Header.Set("Connection", "keep-alive")
}

func setApiHeaders(req *http.Request) {
	setHeader(req)
	req.Header.Set("Origin", BaseURL)
	req.Header.Set("Referer", GoURL)
	req.Header.Set("RoleCode", RoleCode)
	req.Header.Set("X-Requested-With", "XMLHttpRequest")
}

func pauseExit() {
	fmt.Print("\n按回车键退出...")
	bufio.NewReader(os.Stdin).ReadBytes('\n')
}