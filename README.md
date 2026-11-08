# vivant-danmaku

Yahoo!リアルタイム検索の投稿をWindows画面上にニコニコ動画風の弾幕として流すツール。
動画視聴時（TVerなど）に画面の上に重ねて使用します。クリック透過のため、背面のブラウザやプレーヤーの操作を妨げません。

## 必要環境

- Windows 10 / 11
- Python 3.8以上（追加ライブラリのインストール不要）

## 使い方

1. `run.bat` を実行します。
2. 画面上にコメントが流れます。
3. 終了するときは、開いたコンソール画面でEnterキーを押します。

サブモニターに流したい場合は、`.env` の `MONITOR` にモニター番号（2など）を指定するか、コマンドラインで `python danmaku.py --monitor 2` と実行してください。

## 設定

`.env` で動作設定を変更できます。未作成の場合は `.env.example` をコピーして作成してください。

```ini
KEYWORD=VIVANT
FETCH_INTERVAL_SEC=2.0
DELAY_OFFSET_SEC=0
MONITOR=2
ALPHA=0.65
FONT_SIZE_MIN=14
FONT_SIZE_MAX=17
SPEED_MIN=280
SPEED_MAX=400
MAX_CONCURRENT_COMMENTS=14
SPAWN_INTERVAL_SEC=0.35
```

- `KEYWORD`: 検索する単語
- `DELAY_OFFSET_SEC`: コメントの遅延秒数。配信の遅れに合わせてタイミングを調整したいときに指定
- `MONITOR`: 表示先モニターの番号（1, 2...）
- `ALPHA`: ウィンドウの不透明度（0.1〜1.0）

## 免責事項

本ツールは個人利用を目的とした実験的な実装です。
外部サービスの仕様変更や規約変更により動作しなくなる場合があります。本ツールの利用によって生じたいかなる損害についても、開発者は責任を負いません。自己責任でご利用ください。
