import os
import pandas as pd
import requests
from bs4 import BeautifulSoup
import time
import subprocess
import sys
import select

PUBLIC_DIR = "public"
os.makedirs(PUBLIC_DIR, exist_ok=True)

CUSTOM_FILE = os.path.join(PUBLIC_DIR, "custom.csv")

def scrape_and_save():
    df = pd.read_csv("routes.csv")
    keio_group = ["京王線", "京王相模原線", "京王高尾線"]

    keio_results = []
    other_results = []

    for index, row in df.iterrows():
        line_name = row["路線名"]
        url = row["URL"]
        print(f"🚃 {line_name} を取得中...")

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
                print(f"ℹ️ {line_name} は平常運転のためスキップ。")
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
            print(f"❌ {line_name} エラー: {e}")
            continue

    results = []

    if keio_results:
        # 京王に異常があれば、京王だけを出す
        results = keio_results
    elif other_results:
        # 京王は平常で、他に異常があればそれを出す
        results = other_results
    else:
        # 全て平常
        now = time.strftime("%-m月%-d日%H時%M分", time.localtime())
        message = f"首都圏の鉄道路線はおおむね平常運転です。（{now}更新）"
        results.append({
            "路線名": "現在の運行状況：",
            "運行情報": message,
            "ステータス": "平常運転",
        })

    # 結果を保存
    output_path = os.path.join(PUBLIC_DIR, "result.csv")
    pd.DataFrame(results).to_csv(output_path, index=False, encoding="utf-8-sig")
    print(f"✅ {output_path} に保存されました！（{len(results)}件）")



def wait_and_accept_input():
    print("2分待機中です。メッセージがあれば入力してください（Enterでスキップ）：")
    print("⏳ 入力待ち（120秒以内）...")

    timeout = 120  # 2分
    print("👉 入力 > ", end='', flush=True)

    ready, _, _ = select.select([sys.stdin], [], [], timeout)

    if ready:
        user_input = sys.stdin.readline().strip()
        if user_input:
            with open(CUSTOM_FILE, "w", encoding="utf-8") as f:
                f.write(user_input + "\n")
            print(f"\n📥 メッセージを {CUSTOM_FILE} に書き込みました。")
        else:
            print("\n📤 メッセージなし。何も変更しません。")
    else:
        print("\n⌛ 2分経過。自動スキップします。")


def git_push_if_needed():
    # 差分があるか確認
    status = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)
    if status.stdout.strip():  # 変更がある場合のみ push
        try:
            subprocess.run(["git", "add", "."], check=True)
            subprocess.run(["git", "commit", "-m", "Auto update CSV files"], check=True)
            subprocess.run(["git", "push"], check=True)
            print("🚀 GitHub にプッシュしました。")
        except subprocess.CalledProcessError as e:
            print(f"⚠️ Git操作エラー: {e}")
    else:
        print("🟢 変更なし。GitHubへのプッシュはスキップしました。")

if __name__ == "__main__":
    while True:
        scrape_and_save()
        wait_and_accept_input()
        git_push_if_needed()
        print("⏳ Git push後、3分待機します...")
        time.sleep(3 * 60)  # push後の待機（3分）
        print("🔄 ループを再開します。")