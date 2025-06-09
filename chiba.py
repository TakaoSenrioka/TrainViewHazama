import json
import csv
import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime, timedelta
import time
import subprocess

startid = "00180695"  # 車坂上
goalid = "00180769"   # 千葉駅

url = f'https://transfer.navitime.biz/keiseibus/pc/location/BusLocationResult?startId={startid}&goalId={goalid}'

def extract_time(text, prefix):
    m = re.search(rf'{prefix}(\d{{2}}:\d{{2}})', text)
    return m.group(1) if m else ""

def extract_minutes_info(text):
    m = re.search(r'(\d+)分後に到着', text)
    return m.group(1) if m else ""

def extract_required_time(item):
    dnv_pane = item.select_one('.dnvPane')
    if dnv_pane:
        for div in dnv_pane.find_all('div'):
            text = div.get_text(strip=True)
            if '所要時間' in text:
                m = re.search(r'(\d+)', text)
                return m.group(1) if m else ""
    return ""

def subtract_minutes_from_time(time_str, minutes_str):
    try:
        t = datetime.strptime(time_str, "%H:%M")
        minutes = int(minutes_str)
        new_time = t - timedelta(minutes=minutes)
        return new_time.strftime("%H:%M")
    except Exception:
        return ""

def calculate_minutes_diff_from_now(time_str):
    try:
        now = datetime.now()
        leave = datetime.strptime(time_str, "%H:%M")
        leave = leave.replace(year=now.year, month=now.month, day=now.day)
        diff = int((now - leave).total_seconds() / 60)
        return str(diff) if diff >= 0 else "0"
    except Exception:
        return ""

def scrape_prediction_times(url):
    response = requests.get(url)
    response.encoding = 'utf-8'
    html_content = response.text

    soup = BeautifulSoup(html_content, 'html.parser')
    result = []

    for item in soup.select('li.plotList'):
        prediction_times = item.select('.predictionTime')

        last_leave_time = None
        last_minutes_info = None
        last_delay_time = None

        required_time = extract_required_time(item)

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
                last_leave_time = leave_time
                last_minutes_info = minutes_info
                last_delay_time = delay_time

            elif "到着予定" in text:
                arrive_time = extract_time(text, "到着予定:")
                leave_time = last_leave_time or subtract_minutes_from_time(arrive_time, required_time)
                delay_time = last_delay_time if last_delay_time else "0"
                minutes_info = last_minutes_info or calculate_minutes_diff_from_now(leave_time)

                result.append({
                    "leave_time": leave_time,
                    "delay_time": delay_time,
                    "minutes_info": minutes_info,
                    # 以下は不要なので削除
                    # "arrive_time": arrive_time,
                    # "required_time": required_time
                })

                last_leave_time = None
                last_minutes_info = None
                last_delay_time = None

    if not result:
        return {"message": "本日の運転は終了しました。"}
    return result

def save_csv(data):
    output_csv = 'public/chiba_timetable.csv'
    fieldnames = ["leave_time", "delay_time", "minutes_info"]
    with open(output_csv, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in data:
            writer.writerow(row)
    print(f"CSVファイルを {output_csv} に出力しました。")

def git_push():
    try:
        subprocess.run(["git", "add", "public/chiba_timetable.csv"], check=True)
        subprocess.run(["git", "commit", "-m", "Update timetable CSV"], check=True)
        subprocess.run(["git", "push"], check=True)
        print("Git に正常にプッシュしました。")
    except subprocess.CalledProcessError as e:
        print("Gitの操作でエラーが発生しました:", e)

if __name__ == "__main__":
    while True:
        scraped_data = scrape_prediction_times(url)
        if isinstance(scraped_data, list):
            save_csv(scraped_data)
            git_push()
        else:
            print(scraped_data["message"])
        time.sleep(15)
