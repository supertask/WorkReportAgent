import os
import time
import sys
from google import genai
from google.genai import types

def main():
    # APIキーの取得
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        print("エラー: 環境変数 GOOGLE_API_KEY が設定されていません。")
        sys.exit(1)

    # クライアントの初期化
    try:
        client = genai.Client(api_key=api_key)
    except Exception as e:
        print(f"クライアントの初期化に失敗しました: {e}")
        sys.exit(1)

    # 動画ファイルのパス
    video_path = os.path.join(os.path.dirname(__file__), "input", "sample.mp4")
    
    if not os.path.exists(video_path):
        print(f"エラー: 動画ファイルが見つかりません: {video_path}")
        sys.exit(1)

    print(f"動画ファイルをアップロードしています: {video_path}")
    
    try:
        # 動画ファイルのアップロード
        video_file = client.files.upload(file=video_path)
        print(f"アップロード完了: {video_file.name}")
        
        # 処理完了待ち
        print("動画の処理を待機中...")
        while video_file.state.name == "PROCESSING":
            print(".", end="", flush=True)
            time.sleep(2)
            video_file = client.files.get(name=video_file.name)
        
        if video_file.state.name == "FAILED":
            print("\n動画の処理に失敗しました。")
            sys.exit(1)
            
        print(f"\n動画の処理が完了しました。状態: {video_file.state.name}")
        
        # サマリー生成
        print("サマリーを生成中 (モデル: gemini-3.0-pro)...")
        
        # 2025年11月にGemini 3.0 Proがリリースされました。
        try:
            response = client.models.generate_content(
                model="gemini-3.0-pro",
                contents=[
                    video_file,
                    "この動画の内容を日本語で詳細に要約してください。"
                ]
            )
            
            print("\n--- 生成されたサマリー ---")
            print(response.text)
            print("-------------------------")
            
        except Exception as e:
            print(f"\n生成エラー (gemini-3.0-pro): {e}")
            print("Gemini 2.5 Proで再試行します...")
            try:
                response = client.models.generate_content(
                    model="gemini-2.5-pro",
                    contents=[
                        video_file,
                        "この動画の内容を日本語で詳細に要約してください。"
                    ]
                )
                print("\n--- 生成されたサマリー (Gemini 2.5 Pro) ---")
                print(response.text)
                print("-------------------------")
            except Exception as e2:
                print(f"\n生成エラー (gemini-2.5-pro): {e2}")
                print("Gemini 1.5 Proで再試行します...")
                try:
                    response = client.models.generate_content(
                        model="gemini-1.5-pro",
                        contents=[
                            video_file,
                            "この動画の内容を日本語で詳細に要約してください。"
                        ]
                    )
                    print("\n--- 生成されたサマリー (Gemini 1.5 Pro) ---")
                    print(response.text)
                    print("-------------------------")
                except Exception as e3:
                    print(f"\n再試行エラー: {e3}")

    except Exception as e:
        print(f"予期せぬエラーが発生しました: {e}")

if __name__ == "__main__":
    main()

