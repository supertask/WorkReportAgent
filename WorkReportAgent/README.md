# WorkReportAgent

作業動画から日報と作業ログを生成するプロトタイプ。

## 実行手順

### 1. 動画変換
`ffmpeg` 必須。動画をタイムラプス化・圧縮します。

```bash
cd etc/tmp/video_converter
# input/ に動画を置き、config.yml で設定調整可
python3 convert_timelapse.py
```

### 2. 解析・レポート生成
Gemini APIで動画を解析します。

```bash
export GOOGLE_API_KEY="your_key"
cd etc/tmp/vision_test
python3 gemini_video_summary.py [動画パス]
```

## リンク
* [入出力仕様](docs/io_spec.md)
