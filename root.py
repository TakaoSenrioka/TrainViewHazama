import os
import csv
import time
import subprocess
import sys
import select
import requests
import pandas as pd
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import re

# 定数定義
PUBLIC_DIR = "public"
CHIBA_FILE = os.path.join(PUBLIC_DIR, "chiba_timetable.csv")
CUSTOM_FILE = os.path.join(PUBLIC_DIR, "custom.csv")
ROUTES_FILE = "routes.csv"
KEIO_GROUP = ["京王線", "京王相模原線", "京王高尾線"]
CHIBA_UPDATE_INTERVAL = 60  # seconds
ROUTE_UPDATE_INTERVAL = 180  # seconds

os.makedirs(PUBLIC_DIR, exist_ok=True)

# プログラム1: 千葉時刻表スクレイピング
startid = "00180695"  # 車坂上
goalid = "00180769"   # 千葉駅
chiba_url = f'https://transfer.navitime.biz/keiseibus/pc/location/BusLocationResult?startId={startid}&goalId={goalid}'

def extract_time(text, prefix):
    m = re.search(rf'{prefix}(\d{{2}}:\d{{2}})', text)
    return m.group(1) if m else ""

def extract_minutes_info(text):
    m = re.search(r'(\d+)分後に到着', text)
    return m.group(1) if m else ""

def subtract_minutes(time_str, minutes):
    try:
        t = datetime.strptime(time_str, '%H:%M')
        t -= timedelta(minutes=minutes)
        return t.strftime('%H:%M')
    except:
        return "00:00"

def scrape_prediction_times(url):
    response = requests.get(url)
    response.encoding = 'utf-8'
    soup = BeautifulSoup(response.text, 'html.parser')
    result = []
    for item in soup.select('li.plotList'):
        course_name_elem = item.select_one('.courseName')
        prediction_times = item.select('.predictionTime')
        last_leave_time, last_minutes_info, last_delay_time = None, None, None
        for pt in prediction_times:
            text = pt.text.strip().replace('\n', '').replace('\t', '')
            parent = pt.parent
            if "定刻" in text:
                minutes_info = ""
                if parent:
                    for s in parent.stripped_strings:
                        if "分後に到着" in s:
                            minutes_info = extract_minutes_info(s.strip())
                            break
                m = re.search(r'遅れ(\d+)分', text)
                delay_time = m.group(1) if m else ""
                leave_time = extract_time(text, "定刻:")
                last_leave_time, last_minutes_info, last_delay_time = leave_time, minutes_info, delay_time
            elif "到着予定" in text:
                arrive_time = extract_time(text, "到着予定:")
                if arrive_time:
                    leave_time = last_leave_time or subtract_minutes(arrive_time, 19)
                    delay_time = last_delay_time if last_leave_time else "0"
                    minutes_info = last_minutes_info if last_leave_time else "0"
                    result.append({
                        "leave_time": leave_time,
                        "delay_time": delay_time,
                        "minutes_info": minutes_info
                    })
                    last_leave_time = last_minutes_info = last_delay_time = None
    return result if result else [{"leave_time": "00:00", "delay_time": "0", "minutes_info": "0"}]

def save_chiba_csv():
    scraped_data = scrape_prediction_times(chiba_url)
    with open(CHIBA_FILE, 'w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['leave_time', 'delay_time', 'minutes_info'])
        for row in scraped_data:
            writer.writerow([row['leave_time'], row['delay_time'], row['minutes_info']])
    print(f"🚌 千葉データを {CHIBA_FILE} に保存しました。")
    git_push("chiba_timetable.csv 更新")

# プログラム2: 路線運行状況スクレイピング
def scrape_routes():
    df = pd.read_csv(ROUTES_FILE)
    keio_results, other_results = [], []
    for _, row in df.iterrows():
        line_name, url = row["路線名"], row["URL"]
        try:
            response = requests.get(url, timeout=10)
            response.encoding = response.apparent_encoding
            soup = BeautifulSoup(response.text, "html.parser")
            suspend = soup.find("dd", class_="trouble suspend")
            trouble = None if suspend else soup.find("dd", class_="trouble")
            info_text = suspend.get_text(strip=True) if suspend else trouble.get_text(strip=True) if trouble else "平常運転"
            if "見合わせ" in info_text:
                status = "運転見合わせ"
            elif "遅れ" in info_text or "ダイヤが乱れ" in info_text:
                status = "遅延"
            elif "運休" in info_text:
                status = "運休"
            elif "直通運転を中止" in info_text:
                status = "直通運転中止"
            elif info_text == "平常運転":
                continue
            else:
                status = "情報"
            entry = {"路線名": line_name, "運行情報": info_text, "ステータス": status}
            (keio_results if line_name in KEIO_GROUP else other_results).append(entry)
        except Exception as e:
            print(f"❌ {line_name} エラー: {e}")

    results = keio_results or other_results or [{
        "路線名": "現在の運行状況：",
        "運行情報": f"首都圏の鉄道路線はおおむね平常運転です。（{time.strftime('%-m月%-d日%H時%M分')}更新）",
        "ステータス": "平常運転",
    }]

    output_path = os.path.join(PUBLIC_DIR, "result.csv")
    pd.DataFrame(results).to_csv(output_path, index=False, encoding="utf-8-sig")
    print(f"🚃 路線データを {output_path} に保存しました。")
    return output_path

def wait_and_accept_input():
    print("✉️ 2分待機中。メッセージがあれば入力してください（Enterでスキップ）：")
    print("👉 入力 > ", end='', flush=True)
    ready, _, _ = select.select([sys.stdin], [], [], 120)
    if ready:
        user_input = sys.stdin.readline().strip()
        if user_input:
            with open(CUSTOM_FILE, "w", encoding="utf-8") as f:
                f.write(user_input + "\n")
            print(f"📥 メッセージを {CUSTOM_FILE} に書き込みました。")
        else:
            print("📤 メッセージなし。")
    else:
        print("⌛ タイムアウト。スキップします。")

def git_push(message="Auto update"):
    status = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)
    if status.stdout.strip():
        try:
            subprocess.run(["git", "add", "."], check=True)
            subprocess.run(["git", "commit", "-m", message], check=True)
            subprocess.run(["git", "push"], check=True)
            print("🚀 GitHub にプッシュしました。")
        except subprocess.CalledProcessError as e:
            print(f"⚠️ Git操作エラー: {e}")
    else:
        print("🟢 変更なし。GitHubへのプッシュはスキップしました。")

# メインループ
if __name__ == "__main__":
    last_route_time = 0
    while True:
        now = time.time()
        # プログラム1の処理（毎分実行）
        save_chiba_csv()

        # プログラム2の処理（3分ごと）
        if now - last_route_time >= ROUTE_UPDATE_INTERVAL:
            result_path = scrape_routes()
            wait_and_accept_input()
            git_push("運行情報を更新")
            last_route_time = now

        # 次のループまで1秒待機
        time.sleep(CHIBA_UPDATE_INTERVAL)
