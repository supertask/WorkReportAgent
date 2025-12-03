# 作業報告エージェント 入出力

## フロー

```mermaid
graph LR
    subgraph Inputs ["入力"]
        Video["作業動画"]
        Tasks["タスクリスト"]
    end

    Agent["Reporter Agent"]

    subgraph Outputs ["出力"]
        Summary["作業報告書<br>(Markdown/スクショ)"]
        Log["作業ログ<br>(TSV)"]
    end

    Video --> Agent
    Tasks --> Agent
    
    Agent --> Summary
    Agent --> Log
```

## データ仕様

*   **入力**: 2FPS作業動画、タスクリスト、ユーザー指示
*   **処理**: Geminiによる映像解析、タスクマッピング
*   **出力**:
    *   作業報告書(Markdown/スクショ付)
    *   **作業ログ(TSV)**: `アプリ名	開始時刻	終了時刻	作業タイトル	作業タグ	作業手順(Markdown)	スクショ時刻`

### TSV出力例

```tsv
Rhino	14:00	15:30	住宅モデリング(1F)	Design,3D	- フロアプランのインポート\n- 壁・柱の立ち上げ\n- 開口部の調整	15:15
Chrome	15:30	15:45	建材リサーチ	Research	- 外壁材のテクスチャ検索\n- カタログダウンロード	15:40
Rhino	15:45	16:30	レンダリング設定	Visualization	- 太陽光設定\n- マテリアル適用	16:10
```

時間のかかる作業順に並べておく。