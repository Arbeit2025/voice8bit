"""
voice8bit - 8bitボイスメーカー
==============================
WAVファイル（16bit PCM）をアップロードすると、レトロゲーム風の
8bitサウンドに変換してダウンロードできる単一ファイル Flask アプリ。

目次
----
1. 設定（変換レベル定義・上限）
2. WAV 読み込み
3. 変換処理（リサンプル／量子化）
4. WAV 書き出し
5. 画面（HTML）とルーティング

変換は Python 標準ライブラリ（wave / struct / math）のみで行い、
変換後ファイルはメモリ上でのみ扱い、サーバーには保存しない。
"""

from __future__ import annotations

import io
import math
import struct
import wave

from flask import Flask, render_template_string, request, send_file

# ============================
# 1. 設定
# ============================

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # アップロード上限 10MB

# 変換の強さ：目標サンプルレートと量子化ビット数の組み合わせ
LEVELS = {
    "weak": {"label": "弱", "rate": 11025, "bits": 8},
    "medium": {"label": "中", "rate": 8000, "bits": 6},
    "strong": {"label": "強", "rate": 4000, "bits": 4},
}
DEFAULT_LEVEL = "medium"


# ============================
# 2. WAV 読み込み
# ============================


def read_wav(data: bytes):
    """WAVバイト列を読み、(チャンネル別サンプル列のリスト, チャンネル数, サンプルレート) を返す。

    対応形式は 16bit PCM（無圧縮）のみ。それ以外は ValueError を送出する。
    """
    try:
        wf = wave.open(io.BytesIO(data), "rb")
    except (wave.Error, EOFError) as exc:
        raise ValueError("WAVファイルとして読み込めませんでした") from exc
    with wf:
        if wf.getcomptype() != "NONE":
            raise ValueError("圧縮されたWAVには対応していません（16bit PCMのみ）")
        if wf.getsampwidth() != 2:
            raise ValueError("16bit PCM のWAVのみ対応しています")
        n_channels = wf.getnchannels()
        rate = wf.getframerate()
        raw = wf.readframes(wf.getnframes())
    if n_channels < 1:
        raise ValueError("チャンネル数が不正です")
    samples = list(struct.unpack("<%dh" % (len(raw) // 2), raw))
    # インターリーブをチャンネル別に分離
    channels = [samples[ch::n_channels] for ch in range(n_channels)]
    return channels, n_channels, rate


# ============================
# 3. 変換処理
# ============================


def resample_channel(samples, src_rate: int, dst_rate: int):
    """1チャンネル分のサンプル列を線形補間でリサンプルする。"""
    if not samples:
        return []
    if src_rate == dst_rate:
        return list(samples)
    out_len = max(1, round(len(samples) * dst_rate / src_rate))
    if out_len == 1:
        return [samples[0]]
    out = []
    last = len(samples) - 1
    for i in range(out_len):
        pos = i * last / (out_len - 1)
        lo = int(math.floor(pos))
        hi = min(lo + 1, last)
        frac = pos - lo
        out.append(int(round(samples[lo] * (1.0 - frac) + samples[hi] * frac)))
    return out


def quantize(samples, bits: int):
    """サンプル列を bits ビット相当の段階数へ量子化する（値は16bitのまま保持）。"""
    levels = 1 << bits
    step = 65536 // levels
    out = []
    for s in samples:
        idx = (s + 32768) // step
        if idx >= levels:
            idx = levels - 1
        v = idx * step + step // 2 - 32768
        out.append(max(-32768, min(32767, v)))
    return out


# ============================
# 4. WAV 書き出し
# ============================


def write_wav(channels, rate: int) -> bytes:
    """チャンネル別サンプル列を 16bit PCM WAV のバイト列にする。"""
    n_channels = len(channels)
    n_frames = len(channels[0]) if channels else 0
    interleaved = []
    for i in range(n_frames):
        for ch in range(n_channels):
            interleaved.append(channels[ch][i])
    raw = struct.pack("<%dh" % len(interleaved), *interleaved)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(n_channels)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(raw)
    return buf.getvalue()


def convert_wav(data: bytes, level_key: str) -> bytes:
    """WAVバイト列を指定レベルの8bit風サウンドへ変換してバイト列で返す。"""
    level = LEVELS[level_key]
    channels, _n_channels, src_rate = read_wav(data)
    converted = []
    for ch_samples in channels:
        resampled = resample_channel(ch_samples, src_rate, level["rate"])
        converted.append(quantize(resampled, level["bits"]))
    return write_wav(converted, level["rate"])


# ============================
# 5. 画面とルーティング
# ============================

INDEX_HTML = """<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>8bitボイスメーカー | voice8bit</title>
<style>
  body { font-family: sans-serif; margin: 2em auto; max-width: 640px; padding: 0 1em;
         background: #14141f; color: #e8e8f0; }
  h1 { font-size: 1.5em; }
  .card { background: #1f1f2e; border: 2px solid #4a4a6a; border-radius: 8px; padding: 1.2em; }
  .error { background: #5a1f1f; border: 1px solid #a04a4a; border-radius: 6px;
           padding: 0.7em 1em; margin-bottom: 1em; }
  label.level { display: block; margin: 0.4em 0; }
  button { background: #ffd94a; border: none; border-radius: 6px; padding: 0.7em 1.6em;
           font-size: 1em; font-weight: bold; cursor: pointer; margin-top: 1em; }
  .note { color: #a0a0b8; font-size: 0.85em; line-height: 1.6; }
</style>
</head>
<body>
<h1>🎮 8bitボイスメーカー</h1>
<p>WAVファイル（16bit PCM）をアップロードすると、レトロゲーム風の8bitサウンドに変換してダウンロードできます。</p>
{% if error %}<div class="error">{{ error }}</div>{% endif %}
<div class="card">
<form method="post" action="/convert" enctype="multipart/form-data">
  <p><input type="file" name="file" accept=".wav,audio/wav" required></p>
  <p>変換の強さ</p>
  {% for key, lv in levels.items() %}
  <label class="level">
    <input type="radio" name="level" value="{{ key }}" {% if key == default_level %}checked{% endif %}>
    {{ lv.label }}（{{ lv.rate }}Hz / {{ lv.bits }}bit量子化）
  </label>
  {% endfor %}
  <button type="submit">8bit化してダウンロード</button>
</form>
</div>
<p class="note">
・対応形式：16bit PCM の WAV のみ／アップロード上限 10MB<br>
・変換内容：サンプルレートを落とす＋振幅を少ない段階数に量子化する、昔のゲーム機風の荒い音になります<br>
・変換したファイルはサーバーに保存されません（メモリ上でのみ処理します）
</p>
</body>
</html>
"""


@app.route("/", methods=["GET"])
def index():
    return render_template_string(
        INDEX_HTML, levels=LEVELS, default_level=DEFAULT_LEVEL, error=None
    )


def index_with_error(message: str, status: int = 400):
    html = render_template_string(
        INDEX_HTML, levels=LEVELS, default_level=DEFAULT_LEVEL, error=message
    )
    return html, status


@app.route("/convert", methods=["POST"])
def convert():
    uploaded = request.files.get("file")
    if uploaded is None or uploaded.filename == "":
        return index_with_error("ファイルが選択されていません")
    if not uploaded.filename.lower().endswith(".wav"):
        return index_with_error("対応していない形式です。WAVファイルを選んでください")
    level_key = request.form.get("level", DEFAULT_LEVEL)
    if level_key not in LEVELS:
        return index_with_error("変換の強さの指定が不正です")
    data = uploaded.read()
    if not data:
        return index_with_error("ファイルが空です")
    try:
        converted = convert_wav(data, level_key)
    except ValueError as exc:
        return index_with_error(str(exc))
    return send_file(
        io.BytesIO(converted),
        mimetype="audio/wav",
        as_attachment=True,
        download_name="voice8bit_%s.wav" % level_key,
    )


@app.errorhandler(413)
def too_large(_exc):
    return index_with_error("ファイルが大きすぎます（上限 10MB）", status=413)


@app.route("/healthz", methods=["GET"])
def healthz():
    return {"status": "ok"}


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
