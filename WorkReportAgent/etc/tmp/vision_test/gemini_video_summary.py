import os
import time
import sys
import yaml
import json
import cv2
from google import genai
from google.genai import types

def load_config():
    config_path = os.path.join(os.path.dirname(__file__), "config.yml")
    if not os.path.exists(config_path):
        return {"model_name": "gemini-3.0-pro", "fallback_models": ["gemini-2.5-pro", "gemini-1.5-pro"]}
    
    with open(config_path, "r") as f:
        return yaml.safe_load(f)

def extract_frame(video_path, timestamp_str, output_path):
    """
    指定されたタイムスタンプ(MM:SS形式)のフレームを抽出して保存する
    """
    try:
        parts = list(map(int, timestamp_str.split(':')))
        seconds = parts[0] * 60 + parts[1]
        if len(parts) > 2: seconds += parts[2] # HH:MM:SS対応
        
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return False
            
        # FPSを取得してフレーム位置を計算
        fps = cap.get(cv2.CAP_PROP_FPS)
        frame_no = int(fps * seconds)
        
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_no)
        ret, frame = cap.read()
        
        if ret:
            cv2.imwrite(output_path, frame)
        
        cap.release()
        return ret
    except Exception as e:
        print(f"画像抽出エラー: {e}")
        return False

def analyze_structure(client, video_file, model_name):
    """
    フェーズ1: 動画の構造解析とスクショポイントの抽出（JSON出力）
    """
    prompt = """
    あなたは業務改善コンサルタントです。この作業動画から詳細な手順書を作成するための「構成案」を作成してください。
    以下のJSONフォーマットで出力してください。

    ```json
    {
      "title": "レポート全体のタイトル",
      "sections": [
        {
          "id": 1,
          "title": "セクションのタイトル（例: データのインポート）",
          "start_time": "00:00",
          "end_time": "02:30",
          "screenshot_timestamp": "00:45", 
          "screenshot_reason": "操作メニューが表示されている重要な瞬間"
        },
        ...
      ]
    }
    ```
    
    * `sections` は作業の区切りごとに細かく分割してください（1セクション3〜5分程度を目安）。
    * `screenshot_timestamp` はそのセクション内で最も視覚的な情報（UI、設定値、結果など）が重要な瞬間の時間を "MM:SS" で指定してください。
    """

    print(f"動画の構造を解析中 ({model_name})...")
    response = client.models.generate_content(
        model=model_name,
        contents=[video_file, prompt],
        config=types.GenerateContentConfig(
            response_mime_type="application/json" # JSONモードを強制
        )
    )
    return json.loads(response.text)

def write_section_report(client, video_file, model_name, section, image_rel_path):
    """
    フェーズ3: セクションごとの詳細レポート執筆
    """
    img_markdown = f"\n![{section['screenshot_reason']}]({image_rel_path})\n" if image_rel_path else ""
    
    prompt = f"""
    動画の {section['start_time']} から {section['end_time']} までの範囲について、
    「{section['title']}」という見出しで詳細な作業ログを書いてください。

    ## 要件
    1. このセクションで行われた具体的な操作、使用ツール、入力値を箇条書きで列挙すること。
    2. 作業のボトルネックや、逆に効率的な点があれば指摘すること。
    3. 以下の画像をレポート内の適切な位置（操作説明の直後など）に挿入済みとして扱ってください。
       画像の説明: {section['screenshot_reason']}
    
    ## 出力形式
    Markdown形式（見出しは `###` から始めること）
    """

    response = client.models.generate_content(
        model=model_name,
        contents=[video_file, prompt]
    )
    
    # 画像マークダウンを挿入
    return f"\n## {section['title']} ({section['start_time']} - {section['end_time']})\n{img_markdown}\n{response.text}\n"

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
    primary_model = config.get("model_name", "gemini-2.0-flash-exp")
    fallback_models = config.get("fallback_models", [])

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

    # configから設定取得
    include_screenshots = config.get("report", {}).get("include_screenshots", False)
    screenshot_dir_name = config.get("report", {}).get("screenshot_dir", "images")
    
    output_md_path = os.path.join(os.path.dirname(__file__), "output", "Report.md")
    output_img_dir = os.path.join(os.path.dirname(__file__), "output", screenshot_dir_name)
    
    if include_screenshots and not os.path.exists(output_img_dir):
        os.makedirs(output_img_dir)

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

        # --- Phase 1: 構造解析 ---
        try:
            structure = analyze_structure(client, video_file, primary_model)
            print("構造解析完了。セクション数:", len(structure.get("sections", [])))
        except Exception as e:
            print(f"構造解析失敗: {e}")
            sys.exit(1)

        # レポートファイルの初期化
        with open(output_md_path, "w", encoding="utf-8") as f:
            f.write(f"# {structure.get('title', '動画分析レポート')}\n\n")
            f.write("## 概要\nAIによる自動生成レポートです。詳細な手順と分析を含みます。\n\n")

        # --- Phase 2 & 3: ループ処理 ---
        for section in structure.get("sections", []):
            print(f"処理中: {section.get('title', 'Untitled')}...")
            
            # 画像抽出
            image_rel_path = None
            if include_screenshots and "screenshot_timestamp" in section:
                timestamp = section["screenshot_timestamp"]
                # ファイル名に使えない文字を置換
                safe_timestamp = timestamp.replace(':', '-')
                img_filename = f"sec_{section['id']}_{safe_timestamp}.jpg"
                img_full_path = os.path.join(output_img_dir, img_filename)
                
                if extract_frame(video_path, timestamp, img_full_path):
                    image_rel_path = f"./{screenshot_dir_name}/{img_filename}"
                    print(f"  - スクショ保存: {timestamp}")
                else:
                    print(f"  - スクショ失敗: {timestamp}")

            # 詳細執筆
            try:
                section_content = write_section_report(client, video_file, primary_model, section, image_rel_path)
                
                # ファイルに追記 (Step-by-step writing)
                with open(output_md_path, "a", encoding="utf-8") as f:
                    f.write(section_content)
                    f.write("\n---\n") # セパレータ
                    
                print(f"  - 執筆完了")
                time.sleep(2) # レート制限回避のため少し待機
                
            except Exception as e:
                print(f"  - セクション生成エラー: {e}")

        print(f"\n全処理完了。レポート: {output_md_path}")

    except Exception as e:
        print(f"予期せぬエラーが発生しました: {e}")

if __name__ == "__main__":
    main()
