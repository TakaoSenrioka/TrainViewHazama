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

    keio_status = None  # 京王線が異常かどうかを記録するため

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
                print(f"ℹ️ {line_name} は平常運転のため結果に追加しません。")
                status = None  # 平常運転は追加しない
            else:
                status = "情報"

            if status:
                results.append({
                    "路線名": line_name,
                    "運行情報": info_text,
                    "ステータス": status,
                })

            if line_name == "京王線":
                keio_status = status  # None なら平常、文字列なら異常

        except Exception as e:
            print(f"❌ {line_name} エラー: {e}")
            results.append({
                "路線名": line_name,
                "運行情報": "取得エラー",
                "ステータス": "取得失敗",
            })
            if line_name == "京王線":
                keio_status = "取得失敗"

    # 平常運転で何も追加されていない場合は京王線の情報だけ書く
    if not results and keio_status is None:
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
