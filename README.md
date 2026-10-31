# voice8bit（8bitボイスメーカー）

WAVファイル（16bit PCM）をアップロードすると、レトロゲーム風の8bitサウンドに変換してダウンロードできる、単一ファイル Flask の Web ツールです。

## できること

- WAV（16bit PCM）を 8bit 風に変換してダウンロード
  - サンプルレートを落とす（リサンプル）
  - 振幅を少ない段階数に量子化する
- 変換の強さを3段階から選択
  - 弱：11025Hz / 8bit量子化
  - 中：8000Hz / 6bit量子化
  - 強：4000Hz / 4bit量子化
- アップロード上限は 10MB
- 変換は Python 標準ライブラリ（wave / struct / math）のみで実施
- 変換したファイルはサーバーに保存されません（メモリ上でのみ処理）

## 対応形式・制限

- 入力は **16bit PCM の WAV のみ**（モノラル／ステレオ可）
- MP3などの圧縮形式、8bit/24bit WAV、圧縮WAV はエラーになります
- 変換結果も 16bit PCM の WAV として出力します（サンプルレートと量子化で「8bit風」の音にしています）

## ローカル起動

```bash
pip install -r requirements.txt
python app.py
# http://127.0.0.1:5000 を開く
```

## テスト

```bash
python -m unittest discover -s tests
```

## デプロイ（Render）

`render.yaml` を同梱しています。Render の Web Service（Free / Python）として、
ビルド `pip install -r requirements.txt`、起動 `gunicorn app:app` で公開できます。

## 由来

GitHub のフォロワー yumiaura さんの audio8bit（音声を8bit風に変換するCLI）に着想を得て、ブラウザから使える Web 版として作った派生アイデアです。
