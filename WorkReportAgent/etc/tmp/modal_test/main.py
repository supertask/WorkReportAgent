import modal
import os
import base64

# Modalアプリケーションの定義
app = modal.App("video-analyzer-qwen3")

# イメージの定義
# Unsloth/Qwen3-VLを動かすための環境構築
# 最新のtransformersとaccelerate, bitsandbytes (4bit量子化用) を入れる
# flash-attnビルドのためにCUDA develイメージを使用
image = (
    modal.Image.from_registry("nvidia/cuda:12.4.0-devel-ubuntu22.04", add_python="3.11")
    .pip_install(
        "torch",
        "torchvision",
        "transformers",
        "accelerate",
        "bitsandbytes", 
        "qwen-vl-utils",
        "opencv-python-headless",
        "numpy",
        "moviepy",
        "decord",
        "ninja", 
        "packaging",
        "wheel"
    )
    .run_commands(
        "pip install flash-attn --no-build-isolation"
    )
)

# 永続的なボリュームを作成（モデルのキャッシュ用）
model_volume = modal.Volume.from_name("hf-model-cache", create_if_missing=True)

@app.function(
    image=image,
    gpu="A100", # 40GB VRAM。32Bの4bit量子化なら約20GBなので収まるはず
    volumes={"/root/.cache/huggingface": model_volume},
    timeout=3600 # ダウンロードに時間がかかるので長めに
)
def analyze_video_with_unsloth_qwen3(video_bytes: bytes, prompt_text: str):
    import torch
    from transformers import Qwen2_5_VLForConditionalGeneration, AutoProcessor, BitsAndBytesConfig
    from qwen_vl_utils import process_vision_info
    import tempfile

    print("処理を開始します...")
    print("GPUメモリ状況を確認中...")
    print(torch.cuda.get_device_name(0))
    print(f"VRAM: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.2f} GB")

    # --- モデルの設定 ---
    # ユーザー指定: unsloth/Qwen3-VL-32B-Thinking
    # GGUF版はllama.cpp未対応のため、Transformersで4bit量子化して動かす
    # 注: Qwen3-VLはアーキテクチャ的にはQwen2.5-VLの拡張の可能性があるため、
    # AutoModelで読み込めるはずですが、クラス指定が必要な場合は修正します。
    
    model_name = "unsloth/Qwen3-VL-32B-Thinking" 
    # model_name = "unsloth/Qwen3-VL-8B-Thinking" # 動作テスト用

    print(f"モデルをロード中: {model_name} (4bit量子化)")
    
    # 4bit量子化の設定
    quantization_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
    )

    try:
        # Qwen3-VLはAutoClassで読み込めるはず
        from transformers import AutoModelForVision2Seq
        
        model = AutoModelForVision2Seq.from_pretrained(
            model_name,
            quantization_config=quantization_config,
            device_map="auto",
            attn_implementation="flash_attention_2",
        )
        processor = AutoProcessor.from_pretrained(model_name)
        
    except Exception as e:
        print(f"モデルロードエラー: {e}")
        print("Qwen2.5-VLクラスでのロードを試みます...")
        try:
            # Qwen2.5-VLとしてロードを試みる（アーキテクチャが似ている場合）
            model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
                model_name,
                quantization_config=quantization_config,
                device_map="auto",
                attn_implementation="flash_attention_2",
            )
            processor = AutoProcessor.from_pretrained(model_name)
        except Exception as e2:
             return f"Fatal Error loading model: {e2}"

    # --- 動画の一時保存 ---
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as temp_video:
        temp_video.write(video_bytes)
        temp_video_path = temp_video.name

    print("推論を実行中...")
    
    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "video",
                    "video": temp_video_path,
                    "max_pixels": 360 * 420, # 解像度制限
                    "fps": 1.0, 
                },
                {"type": "text", "text": prompt_text},
            ],
        }
    ]

    # 入力の前処理
    text = processor.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True
    )
    image_inputs, video_inputs = process_vision_info(messages)
    
    inputs = processor(
        text=[text],
        images=image_inputs,
        videos=video_inputs,
        padding=True,
        return_tensors="pt",
    )
    inputs = inputs.to(model.device)

    # 生成
    # Thinkingモデルは思考プロセスを出力するためmax_new_tokensを多めに
    generated_ids = model.generate(**inputs, max_new_tokens=1024)
    
    generated_ids_trimmed = [
        out_ids[len(in_ids) :] for in_ids, out_ids in zip(inputs.input_ids, generated_ids)
    ]
    output_text = processor.batch_decode(
        generated_ids_trimmed, skip_special_tokens=True, clean_up_tokenization_spaces=False
    )

    # 後片付け
    os.remove(temp_video_path)

    return output_text[0]


@app.local_entrypoint()
def main():
    input_path = "input/sample.mp4"
    
    if not os.path.exists(input_path):
        print(f"エラー: {input_path} が見つかりません。")
        return

    print(f"ファイル {input_path} を読み込んでいます...")
    with open(input_path, "rb") as f:
        video_data = f.read()

    print("Modal上で処理を開始します (Unsloth Qwen3-VL 4bit)...")
    try:
        result = analyze_video_with_unsloth_qwen3.remote(
            video_bytes=video_data, 
            prompt_text="この動画の内容を詳しく説明してください。"
        )
        print("\n=== 解析結果 ===\n")
        print(result)
    except Exception as e:
        print(f"\nエラーが発生しました: {e}")
