import tkinter as tk
from tkinter import scrolledtext, messagebox
import threading
import queue
import time
import os
import pandas as pd
import requests
from bs4 import BeautifulSoup
import subprocess

PUBLIC_DIR = "public"
CUSTOM_FILE = os.path.join(PUBLIC_DIR, "custom.csv")
CHIBA_DELAY_FILE = os.path.join(PUBLIC_DIR, "chiba_delay.csv")
RESULT_FILE = os.path.join(PUBLIC_DIR, "result.csv")

os.makedirs(PUBLIC_DIR, exist_ok=True)

log_queue = queue.Queue()

def log(msg):
    log_queue.put(msg)

def gui_logger(text_widget):
    while not log_queue.empty():
        msg = log_queue.get()
        text_widget.configure(state='normal')
        text_widget.insert(tk.END, msg + "\n")
        text_widget.configure(state='disabled')
        text_widget.see(tk.END)
    text_widget.after(500, gui_logger, text_widget)

def scrape_and_save():
    df = pd.read_csv("routes.csv")
    keio_group = ["京王線", "京王相模原線", "京王高尾線"]

    keio_results = []
    other_results = []

    for index, row in df.iterrows():
        line_name = row["路線名"]
        url = row["URL"]
        log(f"🚃 {line_name} を取得中...")

        try:
            response = requests.get(url, timeout=10)
            response.encoding = response.apparent_encoding
            soup = BeautifulSoup(response.text, "html.parser")

            suspend = soup.find("dd", class_="trouble suspend")
            trouble = None if suspend else soup.find("dd", class_="trouble")

            if suspend:
                info_text = suspend.get_text(strip=True)
            elif trouble:
                info_text = trouble.get_text(strip=True)
            else:
                info_text = "平常運転"

            if "見合わせ" in info_text:
                status = "運転見合わせ"
            elif "遅れ" in info_text:
                status = "遅延"
            elif "運休" in info_text:
                status = "運休"
            elif "直通運転を中止" in info_text:
                status = "直通運転中止"
            elif "ダイヤが乱れ" in info_text:
                status = "遅延"
            elif info_text == "平常運転":
                log(f"ℹ️ {line_name} は平常運転のためスキップ。")
                continue
            else:
                status = "情報"

            result_entry = {
                "路線名": line_name,
                "運行情報": info_text,
                "ステータス": status,
            }

            if line_name in keio_group:
                keio_results.append(result_entry)
            else:
                other_results.append(result_entry)

        except Exception as e:
            log(f"❌ {line_name} エラー: {e}")
            continue

    results = keio_results if keio_results else other_results

    if not results:
        now = time.strftime("%-m月%-d日%H時%M分", time.localtime())
        message = f"首都圏の鉄道路線はおおむね平常運転です。（{now}更新）"
        results.append({
            "路線名": "現在の運行状況：",
            "運行情報": message,
            "ステータス": "平常運転",
        })

    pd.DataFrame(results).to_csv(RESULT_FILE, index=False, encoding="utf-8-sig")
    log(f"✅ {RESULT_FILE} に保存されました！（{len(results)}件）")

def update_chiba_delay_csv():
    df = pd.read_csv(RESULT_FILE)
    chiba_lines = ["中央・総武線[各駅停車]", "総武線(快速)[東京〜千葉]"]
    chiba_df = df[df["路線名"].isin(chiba_lines)]

    if not chiba_df.empty:
        chiba_df.to_csv(CHIBA_DELAY_FILE, index=False, encoding="utf-8-sig")
        log(f"✅ {CHIBA_DELAY_FILE} に該当路線の情報を保存しました（{len(chiba_df)}件）")
    else:
        now = time.strftime("%-m月%-d日%H時%M分", time.localtime())
        default_message = f"首都圏の鉄道路線はおおむね平常運転です。（{now}更新）"
        df_default = pd.DataFrame([{ "路線名": "現在の運行状況：", "運行情報": default_message, "ステータス": "平常運転" }])
        df_default.to_csv(CHIBA_DELAY_FILE, index=False, encoding="utf-8-sig")
        log(f"ℹ️ {CHIBA_DELAY_FILE} に平常運転のメッセージを書き込みました。")

def update_custom_message(message):
    with open(CUSTOM_FILE, "w", encoding="utf-8") as f:
        f.write(message.strip() + "\n")
    log(f"📥 カスタムメッセージを {CUSTOM_FILE} に書き込みました。")

def run_scrape_all():
    scrape_and_save()
    update_chiba_delay_csv()

def start_scrape():
    threading.Thread(target=run_scrape_all, daemon=True).start()

def on_custom_submit(entry):
    msg = entry.get()
    if msg:
        update_custom_message(msg)
        entry.delete(0, tk.END)
    else:
        messagebox.showinfo("情報", "メッセージを入力してください。")

def build_gui():
    root = tk.Tk()
    root.title("鉄道運行情報 スクレイパー GUI")

    frame = tk.Frame(root)
    frame.pack(padx=10, pady=10)

    log_box = scrolledtext.ScrolledText(frame, width=80, height=20, state='disabled')
    log_box.pack(pady=10)

    btn = tk.Button(frame, text="スクレイピング開始", command=start_scrape)
    btn.pack(pady=5)

    custom_label = tk.Label(frame, text="カスタムメッセージ入力：")
    custom_label.pack()
    custom_entry = tk.Entry(frame, width=60)
    custom_entry.pack()
    custom_button = tk.Button(frame, text="更新", command=lambda: on_custom_submit(custom_entry))
    custom_button.pack(pady=5)

    gui_logger(log_box)
    start_git_push_loop()
    root.mainloop()

def git_push_if_needed():
    status = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)
    if status.stdout.strip():
        try:
            subprocess.run(["git", "add", "."], check=True)
            subprocess.run(["git", "commit", "-m", "Auto update CSV files"], check=True)
            subprocess.run(["git", "push"], check=True)
            log("🚀 GitHub にプッシュしました。")
        except subprocess.CalledProcessError as e:
            log(f"⚠️ Git操作エラー: {e}")
    else:
        log("🟢 変更なし。GitHubへのプッシュはスキップしました。")

def start_git_push_loop():
    def loop():
        while True:
            time.sleep(180)  # 3分
            git_push_if_needed()
    threading.Thread(target=loop, daemon=True).start()


if __name__ == "__main__":
    build_gui()
