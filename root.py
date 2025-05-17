import os
import pandas as pd
import requests
from bs4 import BeautifulSoup
import time
import subprocess

PUBLIC_DIR = "public"
os.makedirs(PUBLIC_DIR, exist_ok=True)

CUSTOM_FILE = os.path.join(PUBLIC_DIR, "custom.csv")

def scrape_and_save():
    df = pd.read_csv("routes.csv")
    results = []

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
            elif info_text == "平常運転":
                # 平常運転なら結果に追加しない
                print(f"ℹ️ {line_name} は平常運転のため結果に追加しません。")
                continue
            else:
                status = "情報"

            results.append({
                "路線名": line_name,
                "運行情報": info_text,
                "ステータス": status,
            })

        except Exception as e:
            print(f"❌ {line_name} エラー: {e}")
            results.append({
                "路線名": line_name,
                "運行情報": "取得エラー",
                "ステータス": "取得失敗",
            })

    if results:
        output_path = os.path.join(PUBLIC_DIR, "result.csv")
        pd.DataFrame(results).to_csv(output_path, index=False, encoding="utf-8-sig")
        print(f"✅ {output_path} に保存されました！")
    else:
        print("ℹ️ すべて平常運転のため、result.csvは更新しません。")


def wait_and_accept_input():
    print("5分待機中です。メッセージがあれば入力してください（Enterでスキップ）：")
    user_input = input().strip()
    if user_input:
        # ファイル全体を置き換え
        with open(CUSTOM_FILE, "w", encoding="utf-8") as f:
            f.write(user_input + "\n")
        print(f"📥 メッセージを {CUSTOM_FILE} に書き込みました。")
    else:
        print("📤 メッセージなし。何も変更しません。")


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
        time.sleep(5 * 60)
