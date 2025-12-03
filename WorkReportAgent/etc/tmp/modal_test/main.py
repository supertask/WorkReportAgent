import modal
import os
import base64

# Modalアプリケーションの定義
app = modal.App("video-analyzer-qwen")

# イメージの定義: CUDAサポート付きのllama-cpp-pythonをインストール
# ビルド時間を短縮するため、必要なシステムライブラリも追加
image = (
    modal.Image.from_registry("nvidia/cuda:12.4.0-devel-ubuntu22.04", add_python="3.11")
    .apt_install("libgl1", "libglib2.0-0", "git", "wget", "cmake", "build-essential")
    .pip_install(
        "huggingface_hub",
        "opencv-python-headless",
        "numpy",
    )
    .run_commands(
        # GPUサポートを有効にしてllama-cpp-pythonをインストール
        "CMAKE_ARGS='-DGGML_CUDA=on' pip install llama-cpp-python --no-cache-dir --force-reinstall --upgrade"
    )
)

# 永続的なボリュームを作成（モデルのキャッシュ用）
model_volume = modal.Volume.from_name("hf-model-cache", create_if_missing=True)

@app.function(
    image=image,
    gpu="A100",  # 32Bモデルを快適に動かすためA100に変更
    volumes={"/root/.cache/huggingface": model_volume}, # キャッシュを永続化
    timeout=1200 # 20分タイムアウト
)
def analyze_video_with_qwen(video_bytes: bytes, prompt: str):
    import cv2
    import numpy as np
    from huggingface_hub import hf_hub_download
    from llama_cpp import Llama, LlamaChatCompletionHandler

    print("処理を開始します...")

    # --- モデルのVRAM要件目安 (Unsloth Dynamic GGUF Q4_K_M + コンテキスト) ---
    # 1. Qwen3-VL-8B-Thinking
    #    - モデルサイズ: 約 6 GB
    #    - 必要VRAM: 8GB〜 (T4, L4, A10G)
    #    - コスト優先ならこちらを選択
    
    # 2. Qwen3-VL-32B-Thinking (現在選択中)
    #    - モデルサイズ: 約 20 GB
    #    - 必要VRAM: 24GB (A10G) だとギリギリ。動画解析(長コンテキスト)には 40GB (A100) 推奨。
    
    # 3. Qwen3-VL-235B-A22B-Thinking (MoE)
    #    - モデルサイズ: 約 140 GB (Q4推計)
    #    - 必要VRAM: 160GB以上 (A100 80GB x 2〜4)
    #    - Modalでは gpu="A100-80GB:2" などの指定が必要
    
    # ユーザー指定: unsloth/Qwen3-VL-32B-Thinking-GGUF
    repo_id = "unsloth/Qwen3-VL-32B-Thinking-GGUF"
    filename = "Qwen3-VL-32B-Thinking-Q4_K_M.gguf" 
    
    print(f"モデルをロード中: {repo_id}/{filename}")
    try:
        model_path = hf_hub_download(repo_id=repo_id, filename=filename)
    except Exception as e:
        print(f"モデルのダウンロードに失敗しました: {e}")
        print("正しいrepo_idとfilenameを指定してください。")
        return "Model download failed"

    # Llama-cppの初期化（GPUレイヤーをオフロード）
    # n_gpu_layers=-1 で全てのレイヤーをGPUに載せる
    # chat_handler=LlamaChatCompletionHandler() はVisionモデルで必要な場合がある
    llm = Llama(
        model_path=model_path,
        n_gpu_layers=-1, # 全てGPU
        n_ctx=8192,      # コンテキスト長
        verbose=True
    )

    # --- 動画の前処理 ---
    # 一時ファイルに保存
    temp_video_path = "/tmp/temp_video.mp4"
    with open(temp_video_path, "wb") as f:
        f.write(video_bytes)

    cap = cv2.VideoCapture(temp_video_path)
    frames = []
    frame_interval = 30 # 30フレームごとに1枚取得（約1秒に1枚）
    count = 0
    
    print("動画からフレームを抽出中...")
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
        if count % frame_interval == 0:
            # JPEGにエンコードしてbase64化
            _, buffer = cv2.imencode('.jpg', frame)
            base64_image = base64.b64encode(buffer).decode('utf-8')
            frames.append(base64_image)
        count += 1
    cap.release()
    print(f"抽出フレーム数: {len(frames)}")

    # --- 推論の実行 ---
    # VLMへの入力形式を作成
    # 注: llama-cpp-pythonのバージョンやモデルによって画像入力の形式が異なります
    # ここではOpenAI互換のChat Completion API形式を使用します
    
    results = []
    
    # 各フレームについて処理（まとめて送ることも可能だが、ここでは1枚ずつ解説させる例）
    for i, img_b64 in enumerate(frames):
        print(f"フレーム {i+1}/{len(frames)} を解析中...")
        
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text", 
                        "text": prompt
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}
                    }
                ]
            }
        ]

        try:
            response = llm.create_chat_completion(
                messages=messages,
                max_tokens=256,
                temperature=0.7
            )
            content = response["choices"][0]["message"]["content"]
            results.append(f"Frame {i+1}: {content}")
            print(f"  -> {content[:50]}...")
        except Exception as e:
            print(f"推論エラー: {e}")
            results.append(f"Frame {i+1}: Error - {str(e)}")

    return "\n\n".join(results)


@app.local_entrypoint()
def main():
    input_path = "input/sample.mp4"
    
    if not os.path.exists(input_path):
        print(f"エラー: {input_path} が見つかりません。")
        return

    print(f"ファイル {input_path} を読み込んでいます...")
    with open(input_path, "rb") as f:
        video_data = f.read()

    print("Modal上で処理を開始します...")
    # リモート関数を呼び出し
    result = analyze_video_with_qwen.remote(
        video_bytes=video_data, 
        prompt="この画像の状況を詳しく説明してください。"
    )

    print("\n=== 解析結果 ===\n")
    print(result)


