import os
import time
import sys
import yaml
from google import genai
from google.genai import types

def load_config():
    config_path = os.path.join(os.path.dirname(__file__), "config.yml")
    if not os.path.exists(config_path):
        return {"model_name": "gemini-3.0-pro", "fallback_models": ["gemini-2.5-pro", "gemini-1.5-pro"]}
    
    with open(config_path, "r") as f:
        return yaml.safe_load(f)

def generate_summary_with_fallback(client, video_file, models):
    """
    指定されたモデルリスト順にサマリー生成を試行する
    """
    prompt = "この動画の内容を日本語で詳細に要約してください。"
    
    for model_name in models:
        print(f"サマリーを生成中 (モデル: {model_name})...")
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=[video_file, prompt]
            )
            print(f"\n--- 生成されたサマリー ({model_name}) ---")
            print(response.text)
            print("-------------------------")
            return True
            
        except Exception as e:
            print(f"\n生成エラー ({model_name}): {e}")
            print("次のモデルで再試行します...")
            
    return False

def main():
    # コマンドライン引数の処理
    if len(sys.argv) > 1:
        video_path = sys.argv[1]
        # 相対パスであれば絶対パスに変換
        if not os.path.isabs(video_path):
            video_path = os.path.abspath(video_path)
    else:
        # デフォルトパス
        video_path = os.path.join(os.path.dirname(__file__), "input", "sample.mp4")

    # 設定の読み込み
    config = load_config()
    primary_model = config.get("model_name", "gemini-3.0-pro")
    fallback_models = config.get("fallback_models", [])

    # 試行するモデルのリストを作成（優先モデル + フォールバック）
    models_to_try = [primary_model] + fallback_models

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
        
        # サマリー生成（フォールバック付き）
        if not generate_summary_with_fallback(client, video_file, models_to_try):
            print("\nすべてのモデルでの生成に失敗しました。")
            sys.exit(1)

    except Exception as e:
        print(f"予期せぬエラーが発生しました: {e}")

if __name__ == "__main__":
    main()
