import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox
import json
import os
import threading
import schedule
import time
from datetime import datetime, timedelta
import akshare as ak
import pandas as pd
from openai import OpenAI
import requests
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup

# ================= UI 主题与全局字体配置 =================
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

FONT_MAIN = ("Microsoft YaHei", 14)
FONT_BOLD = ("Microsoft YaHei", 14, "bold")
FONT_TITLE = ("Microsoft YaHei", 16, "bold")
FONT_LOGO = ("Microsoft YaHei", 22, "bold")
FONT_SMALL = ("Microsoft YaHei", 12)

CONFIG_FILE = "settings_pro.json"
REPORT_DIR = "daily_reports"
if not os.path.exists(REPORT_DIR):
    os.makedirs(REPORT_DIR)

AI_PROVIDERS = {
    "Kimi (Moonshot)": {"url": "https://api.moonshot.cn/v1", "model": "moonshot-v1-32k"},
    "DeepSeek": {"url": "https://api.deepseek.com", "model": "deepseek-chat"},
    "智谱 GLM": {"url": "https://open.bigmodel.cn/api/paas/v4", "model": "glm-4-flash"},
    "豆包 (Volcengine)": {"url": "https://ark.cn-beijing.volces.com/api/v3", "model": "ep-xxxxxx"},
    "自定义 (兼容 OpenAI)": {"url": "", "model": ""}
}

class ModernStockApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("AI智能量化投研平台 V2.2 - 高定界面版 | By JackBlackman")
        self.geometry("1200x800")
        self.minsize(1000, 700)
        
        self.config = self.load_config()
        self.client = None
        self.init_ai_client()

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # ================= 左侧导航栏 =================
        self.sidebar_frame = ctk.CTkFrame(self, width=240, corner_radius=0, fg_color="#11111B")
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
        self.sidebar_frame.grid_rowconfigure(5, weight=1)

        self.logo_label = ctk.CTkLabel(self.sidebar_frame, text="✨ 投研引擎 V2.2", font=FONT_LOGO, text_color="#CBA6F7")
        self.logo_label.grid(row=0, column=0, padx=20, pady=(45, 5))
        self.sub_logo = ctk.CTkLabel(self.sidebar_frame, text="(っ´Ι`)っ By JackBlackman", font=FONT_SMALL, text_color="#A6ADC8")
        self.sub_logo.grid(row=1, column=0, padx=20, pady=(0, 40))

        self.btn_dashboard = self.create_nav_button("💻  监控控制台", 2, self.show_dashboard)
        self.btn_history = self.create_nav_button("📂  历史研报库", 3, self.show_history)
        self.btn_settings = self.create_nav_button("⚙️  核心与配置", 4, self.show_settings)

        self.status_label = ctk.CTkLabel(self.sidebar_frame, text="● 系统初始化中...", text_color="#A6ADC8", font=FONT_SMALL)
        self.status_label.grid(row=6, column=0, padx=20, pady=25, sticky="sw")

        # ================= 右侧主内容区 =================
        self.main_frame = ctk.CTkFrame(self, corner_radius=0, fg_color="#181825")
        self.main_frame.grid(row=0, column=1, sticky="nsew")
        self.main_frame.grid_rowconfigure(0, weight=1)
        self.main_frame.grid_columnconfigure(0, weight=1)

        self.frame_dashboard = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.frame_history = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.frame_settings = ctk.CTkFrame(self.main_frame, fg_color="transparent")

        self.setup_dashboard()
        self.setup_history()
        self.setup_settings()

        self.show_dashboard()

        self.schedule_thread = threading.Thread(target=self.run_schedule, daemon=True)
        self.schedule_thread.start()
        self.apply_schedule()

    def create_nav_button(self, text, row, command):
        btn = ctk.CTkButton(self.sidebar_frame, text=text, anchor="w", height=50, font=FONT_BOLD,
                            command=command, fg_color="transparent", text_color="#CDD6F4", hover_color="#313244", corner_radius=10)
        btn.grid(row=row, column=0, padx=15, pady=8, sticky="ew")
        return btn

    def hide_all_frames(self):
        self.frame_dashboard.grid_forget()
        self.frame_history.grid_forget()
        self.frame_settings.grid_forget()
        for btn in [self.btn_dashboard, self.btn_history, self.btn_settings]:
            btn.configure(fg_color="transparent", text_color="#CDD6F4")

    def show_dashboard(self):
        self.hide_all_frames()
        self.frame_dashboard.grid(row=0, column=0, sticky="nsew", padx=25, pady=25)
        self.btn_dashboard.configure(fg_color="#313244", text_color="#FFFFFF")

    def show_history(self):
        self.hide_all_frames()
        self.frame_history.grid(row=0, column=0, sticky="nsew", padx=25, pady=25)
        self.btn_history.configure(fg_color="#313244", text_color="#FFFFFF")

    def show_settings(self):
        self.hide_all_frames()
        self.frame_settings.grid(row=0, column=0, sticky="nsew", padx=25, pady=25)
        self.btn_settings.configure(fg_color="#313244", text_color="#FFFFFF")

    # ================= 1. 控制台 UI (重构) =================
    def setup_dashboard(self):
        self.frame_dashboard.grid_rowconfigure(1, weight=1)
        self.frame_dashboard.grid_columnconfigure(0, weight=1)
        
        # 独立的控制面板卡片
        control_card = ctk.CTkFrame(self.frame_dashboard, fg_color="#1E1E2E", corner_radius=15)
        control_card.grid(row=0, column=0, sticky="ew", pady=(0, 20))
        
        ctk.CTkLabel(control_card, text="快捷操作台", font=FONT_TITLE, text_color="#A6ADC8").pack(side="left", padx=20, pady=20)

        btn_run = ctk.CTkButton(control_card, text="🚀 立即生成今日策略", font=FONT_BOLD, height=45, corner_radius=8,
                                fg_color="#F5C2E7", hover_color="#EBA0AC", text_color="#11111B",
                                command=lambda: self.run_task_thread(self.task_analyze, "手动即时版"))
        btn_run.pack(side="right", padx=(10, 20), pady=15)

        btn_review = ctk.CTkButton(control_card, text="⏳ 复盘昨日异动", font=FONT_BOLD, height=45, corner_radius=8,
                                   fg_color="#89DCEB", hover_color="#74C7EC", text_color="#11111B",
                                   command=lambda: self.run_task_thread(self.task_review))
        btn_review.pack(side="right", padx=(10, 10), pady=15)

        # 终端日志区
        self.log_area = ctk.CTkTextbox(self.frame_dashboard, font=FONT_MAIN, 
                                       corner_radius=15, fg_color="#11111B", border_color="#313244", border_width=1)
        self.log_area.grid(row=1, column=0, sticky="nsew")
        
        welcome_text = """(ﾉ>ω<)ﾉ 终端启动成功！
引擎版本: V2.2 (SaaS 高定界面与穿甲爬虫版)

✨ 本次更新亮点：
1. 全新精美的卡片式界面布局，操作更加直观。
2. 深度优化的多线程架构，界面丝滑无卡顿。
3. 自动穿甲爬虫（已修复财联社、人民网、环球网拦截问题）。

【提示】请前往“核心与配置”绑定您的模型秘钥与自选股代码。
"""
        self.log_to_ui(welcome_text)

    # ================= 2. 历史报告 UI =================
    def setup_history(self):
        self.frame_history.grid_rowconfigure(1, weight=1)
        self.frame_history.grid_columnconfigure(0, weight=1)
        
        control_card = ctk.CTkFrame(self.frame_history, fg_color="#1E1E2E", corner_radius=15)
        control_card.grid(row=0, column=0, sticky="ew", pady=(0, 20))
        
        ctk.CTkLabel(control_card, text="报告检索", font=FONT_TITLE, text_color="#A6ADC8").pack(side="left", padx=20, pady=20)
        
        ctk.CTkButton(control_card, text="📄 今日报告", command=lambda: self.view_history(0), height=40, font=FONT_BOLD, fg_color="#313244", hover_color="#45475A").pack(side="right", padx=(10, 20), pady=15)
        ctk.CTkButton(control_card, text="📄 昨日报告", command=lambda: self.view_history(1), height=40, font=FONT_BOLD, fg_color="#313244", hover_color="#45475A").pack(side="right", padx=(10, 10), pady=15)

        self.history_area = ctk.CTkTextbox(self.frame_history, font=FONT_MAIN, corner_radius=15, fg_color="#11111B", border_color="#313244", border_width=1)
        self.history_area.grid(row=1, column=0, sticky="nsew")

    # ================= 3. 系统配置 UI (卡片式重构) =================
    def setup_settings(self):
        scroll_frame = ctk.CTkScrollableFrame(self.frame_settings, fg_color="transparent")
        scroll_frame.pack(fill="both", expand=True)
        scroll_frame.grid_columnconfigure(0, weight=1)
        
        def create_card(title, color):
            card = ctk.CTkFrame(scroll_frame, fg_color="#1E1E2E", corner_radius=15)
            card.grid(column=0, sticky="ew", pady=(0, 20))
            card.grid_columnconfigure(1, weight=1)
            ctk.CTkLabel(card, text=title, font=FONT_TITLE, text_color=color).grid(row=0, column=0, columnspan=2, sticky="w", padx=20, pady=(20, 10))
            return card

        def add_row(parent, row_idx, label_text, config_key, is_pwd=False, placeholder=""):
            ctk.CTkLabel(parent, text=label_text, font=FONT_BOLD).grid(row=row_idx, column=0, padx=(20, 10), pady=15, sticky="w")
            entry = ctk.CTkEntry(parent, show="*" if is_pwd else "", placeholder_text=placeholder, height=40, font=FONT_MAIN, fg_color="#11111B", border_color="#313244")
            entry.grid(row=row_idx, column=1, padx=(0, 20), pady=15, sticky="ew")
            entry.insert(0, self.config.get(config_key, ""))
            return entry

        # --- Card 1: AI 模型配置 ---
        card_ai = create_card("🧠 大语言模型 (LLM) 核心配置", "#F5C2E7")
        ctk.CTkLabel(card_ai, text="⚡ 预设模型捷径:", font=FONT_BOLD).grid(row=1, column=0, padx=(20, 10), pady=15, sticky="w")
        self.combo_provider = ctk.CTkComboBox(card_ai, values=list(AI_PROVIDERS.keys()), command=self.on_provider_change, height=40, font=FONT_MAIN, fg_color="#11111B", border_color="#313244")
        self.combo_provider.grid(row=1, column=1, padx=(0, 20), pady=15, sticky="ew")
        self.combo_provider.set(self.config.get("provider", "Kimi (Moonshot)"))
        self.entry_api = add_row(card_ai, 2, "🔑 API Key (必填):", "api_key", True)
        self.entry_base_url = add_row(card_ai, 3, "🔗 Base URL:", "base_url")
        self.entry_model = add_row(card_ai, 4, "🏷️ Model Name:", "model_name")

        # --- Card 2: 盯盘配置 ---
        card_stock = create_card("🎯 自选股基精准盯盘", "#A6E3A1")
        self.entry_stocks = add_row(card_stock, 1, "代码 (逗号分隔):", "my_stocks", False, "例: 600519,300750")
        self.entry_funds = add_row(card_stock, 2, "自选基金:", "my_funds", False, "例: 510300,159915")

        # --- Card 3: 推送与定时 ---
        card_push = create_card("📡 推送路由与自动化调度", "#F38BA8")
        
        ctk.CTkLabel(card_push, text="🔔 启用全局推送:", font=FONT_BOLD).grid(row=1, column=0, padx=(20, 10), pady=15, sticky="w")
        self.switch_push = ctk.CTkSwitch(card_push, text="开启后自动推送到手机", font=FONT_MAIN)
        self.switch_push.grid(row=1, column=1, padx=(0, 20), pady=15, sticky="w")
        if self.config.get("push_enabled"): self.switch_push.select()

        ctk.CTkLabel(card_push, text="📨 推送渠道:", font=FONT_BOLD).grid(row=2, column=0, padx=(20, 10), pady=15, sticky="w")
        self.combo_push = ctk.CTkComboBox(card_push, values=["Server酱", "AstrBot (Webhook)"], height=40, font=FONT_MAIN, fg_color="#11111B", border_color="#313244")
        self.combo_push.grid(row=2, column=1, padx=(0, 20), pady=15, sticky="ew")
        self.combo_push.set(self.config.get("push_method", "Server酱"))

        self.entry_push = add_row(card_push, 3, "📱 Server酱 Key:", "serverchan_key", True)
        self.entry_webhook = add_row(card_push, 4, "🔗 Webhook URL:", "webhook_url", False)
        
        self.entry_t1 = add_row(card_push, 5, "⏰ 早盘策略时间:", "time_1")
        self.entry_t2 = add_row(card_push, 6, "⏰ 午盘动态时间:", "time_2")
        self.entry_t3 = add_row(card_push, 7, "⏰ 收盘总结时间:", "time_3")
        self.entry_tr = add_row(card_push, 8, "🔄 次日复盘时间:", "review_time")

        # 保存按钮
        save_btn = ctk.CTkButton(scroll_frame, text="💾 立即保存并重启引擎", font=FONT_TITLE, 
                                 height=55, corner_radius=10, fg_color="#A6E3A1", hover_color="#94CB90", text_color="#11111B", command=self.save_settings)
        save_btn.grid(row=99, column=0, pady=(20, 50), sticky="ew", padx=20)

    def on_provider_change(self, choice):
        if choice in AI_PROVIDERS and choice != "自定义 (兼容 OpenAI)":
            self.entry_base_url.delete(0, tk.END)
            self.entry_base_url.insert(0, AI_PROVIDERS[choice]["url"])
            self.entry_model.delete(0, tk.END)
            self.entry_model.insert(0, AI_PROVIDERS[choice]["model"])

    # ================= 穿甲级直连爬虫 =================
    def scrape_custom_news(self):
        news_list = []
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }
        
        try:
            res = requests.get("https://www.cls.cn/nodeapi/telegraphList?rn=10", headers=headers, timeout=10)
            for item in res.json().get('data', {}).get('roll_data', []):
                content = item.get('content', '') or item.get('title', '')
                if content: news_list.append("【财联社】" + content[:100].replace('\n', ''))
            self.log_to_ui(" -> ✅ 财联社快讯直连抓取成功！")
        except Exception as e: self.log_to_ui(f" -> ❌ 财联社直连失败：{str(e)[:50]}")

        try:
            res = requests.get("http://www.people.com.cn/rss/politics.xml", headers=headers, timeout=10)
            root = ET.fromstring(res.content) # 解决乱码
            for item in root.findall('.//item')[:5]:
                news_list.append("【人民网】" + item.find('title').text)
            self.log_to_ui(" -> ✅ 人民网RSS抓取成功！")
        except Exception as e: self.log_to_ui(f" -> ❌ 人民网直连失败：{str(e)[:50]}")

        try:
            res = requests.get("https://finance.huanqiu.com/", headers=headers, timeout=10)
            res.encoding = 'utf-8'
            soup = BeautifulSoup(res.text, 'html.parser')
            links = soup.find_all('a')
            count = 0
            for link in links:
                title = link.get_text().strip()
                if len(title) > 12: 
                    news_list.append("【环球网】" + title)
                    count += 1
                if count >= 5: break
            self.log_to_ui(" -> ✅ 环球网原生直连爬虫抓取成功！")
        except Exception as e:
            self.log_to_ui(f" -> ❌ 环球网解析失败：{str(e)[:50]}")

        return "\n".join(news_list) if news_list else "【爬虫被拦截，暂无宏观数据】"

    def get_tencent_hot_stocks(self):
        try:
            url = "http://stock.gtimg.cn/data/index.php?appn=rank&t=ranka/chr&p=1&o=0&l=10&v=list_data"
            res = requests.get(url, timeout=5)
            if "='" not in res.text: return "【暂无热股榜数据】"
                
            data_str = res.text.split("='")[1].split("';")[0]
            stock_list = data_str.split('^')
            hot_names = [s.split(',')[1] for s in stock_list if s and len(s.split(','))>=2]
            if hot_names:
                self.log_to_ui(" -> ✅ 腾讯底层接口：实时涨幅(热股)榜抓取成功！")
                return "、".join(hot_names)
            return "【暂无热股榜数据】"
        except: return "【暂无热股榜数据】"

    def get_tencent_stock_data(self, code):
        prefix = 'sh' if str(code).startswith('6') else 'sz'
        try:
            res = requests.get(f"http://qt.gtimg.cn/q={prefix}{code}", timeout=3)
            data = res.text.split('~')
            if len(data) > 3: return f"股票 {code}({data[1]})：最新价 {data[3]}，今日涨跌幅 {data[32]}%"
        except: pass
        return f"股票 {code}：获取异常"

    def get_comprehensive_data(self):
        self.log_to_ui("\n(*^▽^*) 开始拉取数据：1. 宏观新闻 (多路并发穿甲爬虫启动)...")
        news = self.scrape_custom_news()

        self.log_to_ui("\n(๑•̀ㅂ•́)و✧ 开始拉取数据：2. 今日热股榜 (切入腾讯底层行情网络)...")
        hot_stocks = self.get_tencent_hot_stocks()

        my_stocks_data = ""
        stock_codes = [s.strip() for s in self.config.get("my_stocks", "").split(",") if s.strip()]
        if stock_codes:
            self.log_to_ui("\n📊 测算数据：3. 自选股状态 (AKShare 均线测算 + 专属情报搜索)...")
            my_stocks_data = "\n【用户自选股状态与专属情报】\n"
            for code in stock_codes:
                stock_info = ""
                try: 
                    df = ak.stock_zh_a_hist(symbol=code, period="daily", adjust="qfq")
                    if len(df) >= 20:
                        close = df['收盘'].iloc[-1]
                        ma5, ma20 = df['收盘'].tail(5).mean(), df['收盘'].tail(20).mean()
                        stock_info += f"股票 {code}：最新 {close:.2f} (MA5={ma5:.2f}, MA20={ma20:.2f})\n"
                except: stock_info += self.get_tencent_stock_data(code) + "\n"
                
                try: 
                    news_df = ak.stock_news_em(symbol=code)
                    if not news_df.empty:
                        latest_news = news_df['新闻标题'].head(2).tolist()
                        stock_info += f"  ➤ 个股专属情报: {' | '.join(latest_news)}\n"
                except: stock_info += "  ➤ 个股专属情报: 暂无最新突发消息\n"
                my_stocks_data += stock_info

        my_funds_data = ""
        fund_codes = [f.strip() for f in self.config.get("my_funds", "").split(",") if f.strip()]
        if fund_codes:
            self.log_to_ui("\n📈 测算数据：4. 自选基金盘面 (开启底层重仓股穿透)...")
            my_funds_data = "\n【用户自选基金状态与重仓穿透】\n"
            for code in fund_codes:
                fund_info = ""
                try: 
                    df = ak.fund_etf_hist_em(symbol=code, period="daily", adjust="qfq")
                    fund_info += f"场内基金 {code}：最新 {df['收盘'].iloc[-1]:.3f}\n"
                except:
                    try: 
                        df_open = ak.fund_open_fund_info_em(fund=code, indicator="单位净值走势")
                        fund_info += f"场外基金 {code}：最新净值 {df_open['单位净值'].iloc[-1]:.4f}\n"
                    except: fund_info += f"基金 {code}：无法获取最新价格\n"

                try: 
                    hold_df = ak.fund_portfolio_hold_em(symbol=code)
                    if not hold_df.empty:
                        top_5 = hold_df['股票名称'].head(5).tolist()
                        fund_info += f"  ➤ 基金底层重仓穿透: {', '.join(top_5)}\n"
                except: fund_info += "  ➤ 基金底层重仓穿透: 暂无持仓明细\n"
                my_funds_data += fund_info
        
        return news, hot_stocks, my_stocks_data + my_funds_data

    # ================= AI 与 智能重试路由 =================
    def push_message(self, title, content):
        if not self.config.get("push_enabled"): return
        push_type = self.config.get("push_method", "Server酱")
        self.log_to_ui(f"🚀 触发推送网关，目标通道：{push_type}...")

        if push_type == "Server酱":
            sendkey = self.config.get("serverchan_key", "")
            if sendkey:
                try:
                    requests.post(f"https://sctapi.ftqq.com/{sendkey}.send", data={"title": title, "desp": content[:800]})
                    self.log_to_ui("🔔 Server酱 推送成功！")
                except Exception as e: self.log_to_ui(f"❌ Server酱失败: {e}")

        elif push_type == "AstrBot (Webhook)":
            webhook_url = self.config.get("webhook_url", "")
            if webhook_url:
                try:
                    payload = {"type": "text", "title": title, "message": f"【{title}】\n\n{content}"}
                    requests.post(webhook_url, json=payload, headers={'Content-Type': 'application/json'}, timeout=10)
                    self.log_to_ui("✨ AstrBot/Webhook 推送成功！")
                except Exception as e: self.log_to_ui(f"❌ Webhook失败: {e}")

    def call_ai(self, prompt, max_retries=3):
        if not self.client: return "❌ 引擎错误：未配置 API Key。"
        provider_name = self.config.get("provider", "未知模型")
        model_name = self.config.get("model_name", "moonshot-v1-32k")
        
        for attempt in range(max_retries):
            try:
                response = self.client.chat.completions.create(
                    model=model_name,
                    messages=[{"role": "user", "content": prompt}]
                )
                return response.choices[0].message.content
            except Exception as e:
                err_str = str(e).lower()
                if "429" in err_str or "overloaded" in err_str:
                    self.log_to_ui(f"⏳ {provider_name} 触发官方限流保护，3秒后进行第 {attempt+1}/{max_retries} 次重试连接...")
                    time.sleep(3)
                    continue
                return f"❌ AI 调用失败 ({provider_name}): {e}"
                
        return "❌ 策略生成失败：大模型服务器持续拥堵。建议稍后再试，或在设置中切换为 DeepSeek 等其他模型。"

    def task_analyze(self, time_slot="定时分析"):
        news, hot_stocks, tech_data = self.get_comprehensive_data()
        provider_name = self.config.get("provider", "未命名模型")
        model_name = self.config.get("model_name", "moonshot-v1-32k")
        self.log_to_ui(f"\n🧠 数据汇聚完毕，启动【{provider_name} - {model_name}】大模型进行深度推理...")
        
        prompt = f"""
        现在是 {time_slot}。你是一个顶尖的量化私募研究员。请结合以下数据进行深度分析：
        【宏观头条】: {news}
        【今日市场资金热点股(基于腾讯行情)】: {hot_stocks}
        {tech_data}
        
        【请严格输出以下4点结构】：
        1. 宏观异动总结（提炼最重要的头条资讯）
        2. 热点情绪分析（结合热股榜，推测市场资金炒作什么逻辑？）
        3. 自选股与基金专属诊断（结合数据给出明确短线操作建议）
        4. 总体操作策略与风险提示。
        """
        
        result = self.call_ai(prompt)
        report = f"【{time_slot} 智能投研策略】\n{result}"
        self.save_report(report)
        
        self.log_to_ui(f"\n{'='*20} 以下为 AI 研报原文 {'='*20}\n" + report + f"\n{'='*55}\n")
        self.log_to_ui("(≧∇≦)ﾉ 策略已生成并落盘入库！")
        self.push_message(f"AI投研: {time_slot}策略更新", report)

    def task_review(self):
        self.log_to_ui("\n开始执行盘前复盘...")
        yesterday_report = self.read_history(1)
        prompt = f"你是量化复盘专家。请检视昨日研报准确度，并给出今日防守点位提示。\n【昨日研报】\n{yesterday_report}"
        result = self.call_ai(prompt)
        report = f"【盘前自动复盘：温故知新】\n{result}"
        self.save_report(report)
        self.log_to_ui(f"\n{'='*20} 以下为 AI 研报原文 {'='*20}\n" + report + f"\n{'='*55}\n")
        self.push_message("AI投研: 盘前复盘报告", report)

    # ================= 辅助功能 =================
    def run_task_thread(self, task_func, *args):
        threading.Thread(target=task_func, args=args, daemon=True).start()

    def log_to_ui(self, message):
        time_str = datetime.now().strftime("%H:%M:%S")
        self.log_area.insert(tk.END, f"[{time_str}] {message}\n")
        self.log_area.see(tk.END)

    def save_report(self, content):
        today_str = datetime.now().strftime("%Y-%m-%d")
        with open(os.path.join(REPORT_DIR, f"{today_str}.txt"), "a", encoding="utf-8") as f:
            f.write("\n" + "="*50 + "\n" + content + "\n" + "="*50 + "\n")

    def read_history(self, days_ago):
        target_date = (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%d")
        path = os.path.join(REPORT_DIR, f"{target_date}.txt")
        return open(path, "r", encoding="utf-8").read() if os.path.exists(path) else "无记录。"

    def view_history(self, days_ago):
        self.history_area.delete(1.0, tk.END)
        self.history_area.insert(tk.END, self.read_history(days_ago))

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                if not cfg.get("provider"): cfg["provider"] = "Kimi (Moonshot)"
                return cfg
        return {
            "provider": "Kimi (Moonshot)", "api_key": "", "base_url": "https://api.moonshot.cn/v1",
            "model_name": "moonshot-v1-32k", "push_enabled": True, "push_method": "Server酱",
            "serverchan_key": "", "webhook_url": "http://127.0.0.1:xxx/send",
            "my_stocks": "600519,300750", "my_funds": "510300,159915",
            "time_1": "10:00", "time_2": "12:00", "time_3": "15:00", "review_time": "09:15"
        }

    def save_settings(self):
        self.config["provider"] = self.combo_provider.get()
        self.config["api_key"] = self.entry_api.get()
        self.config["base_url"] = self.entry_base_url.get()
        self.config["model_name"] = self.entry_model.get()
        self.config["push_enabled"] = bool(self.switch_push.get())
        self.config["push_method"] = self.combo_push.get()
        self.config["serverchan_key"] = self.entry_push.get()
        self.config["webhook_url"] = self.entry_webhook.get()
        self.config["my_stocks"] = self.entry_stocks.get()
        self.config["my_funds"] = self.entry_funds.get()
        self.config["time_1"] = self.entry_t1.get()
        self.config["time_2"] = self.entry_t2.get()
        self.config["time_3"] = self.entry_t3.get()
        self.config["review_time"] = self.entry_tr.get()
        
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(self.config, f, indent=4)
        
        self.init_ai_client()
        self.apply_schedule()
        messagebox.showinfo("配置成功", "系统配置已保存！高级SaaS界面引擎已重载。")

    def init_ai_client(self):
        api_key = self.config.get("api_key", "")
        base_url = self.config.get("base_url", "https://api.moonshot.cn/v1")
        if api_key and base_url:
            self.client = OpenAI(api_key=api_key, base_url=base_url)
        else:
            self.client = None

    def apply_schedule(self):
        schedule.clear()
        try:
            schedule.every().day.at(self.config["review_time"]).do(self.task_review)
            for t_idx in [1, 2, 3]:
                t_val = self.config[f"time_{t_idx}"]
                schedule.every().day.at(t_val).do(self.task_analyze, time_slot=f"自动监控 {t_val}")
            self.status_label.configure(text="🟢 AI 引擎挂载就绪 (运行中)", text_color="#A6E3A1")
        except:
            self.status_label.configure(text="🔴 调度异常，请检查时间格式", text_color="#F38BA8")

    def run_schedule(self):
        while True:
            schedule.run_pending()
            time.sleep(10)

if __name__ == "__main__":
    app = ModernStockApp()
    app.mainloop()