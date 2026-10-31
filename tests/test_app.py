import importlib.util
import io
import math
import os
import struct
import unittest
import wave

APP_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app.py"
)


def load_app():
    spec = importlib.util.spec_from_file_location("voice8bit_app", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mod = load_app()


def make_wav_bytes(rate=44100, seconds=0.1, freq=440.0, channels=1, sampwidth=2):
    """テスト用の小さな正弦波WAVバイト列を作る。"""
    n_frames = int(rate * seconds)
    frames = []
    for i in range(n_frames):
        v = int(12000 * math.sin(2 * math.pi * freq * i / rate))
        for _ch in range(channels):
            frames.append(v)
    if sampwidth == 2:
        raw = struct.pack("<%dh" % len(frames), *frames)
    else:  # 8bit WAV（符号なし）— 拒否テスト用
        raw = bytes((v // 256 + 128) & 0xFF for v in frames)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sampwidth)
        wf.setframerate(rate)
        wf.writeframes(raw)
    return buf.getvalue()


def parse_wav(data):
    with wave.open(io.BytesIO(data), "rb") as wf:
        params = {
            "channels": wf.getnchannels(),
            "sampwidth": wf.getsampwidth(),
            "rate": wf.getframerate(),
            "frames": wf.getnframes(),
        }
        raw = wf.readframes(params["frames"])
    samples = list(struct.unpack("<%dh" % (len(raw) // 2), raw))
    return params, samples


class Voice8bitTest(unittest.TestCase):
    def setUp(self):
        self.client = mod.app.test_client()

    def post_wav(self, data, level="medium", filename="test.wav"):
        return self.client.post(
            "/convert",
            data={"file": (io.BytesIO(data), filename), "level": level},
            content_type="multipart/form-data",
        )

    def test_index_ok(self):
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("8bitボイスメーカー", res.get_data(as_text=True))

    def test_convert_medium_rate(self):
        res = self.post_wav(make_wav_bytes(rate=44100), level="medium")
        self.assertEqual(res.status_code, 200)
        params, _samples = parse_wav(res.data)
        self.assertEqual(params["rate"], 8000)
        self.assertEqual(params["sampwidth"], 2)

    def test_convert_weak_rate_and_length(self):
        src = make_wav_bytes(rate=44100, seconds=0.2)
        res = self.post_wav(src, level="weak")
        self.assertEqual(res.status_code, 200)
        params, _samples = parse_wav(res.data)
        self.assertEqual(params["rate"], 11025)
        expected = round(int(44100 * 0.2) * 11025 / 44100)
        self.assertAlmostEqual(params["frames"], expected, delta=2)

    def test_quantize_levels_strong(self):
        res = self.post_wav(make_wav_bytes(), level="strong")
        self.assertEqual(res.status_code, 200)
        params, samples = parse_wav(res.data)
        self.assertEqual(params["rate"], 4000)
        # 4bit量子化なので固有値は16以下
        self.assertLessEqual(len(set(samples)), 16)

    def test_quantize_levels_medium(self):
        res = self.post_wav(make_wav_bytes(), level="medium")
        _params, samples = parse_wav(res.data)
        # 6bit量子化なので固有値は64以下
        self.assertLessEqual(len(set(samples)), 64)

    def test_quantize_function_direct(self):
        out = mod.quantize([0, 100, -100, 32767, -32768], 4)
        self.assertEqual(len(out), 5)
        self.assertLessEqual(len(set(mod.quantize(list(range(-32768, 32768, 97)), 4))), 16)

    def test_stereo_preserved(self):
        res = self.post_wav(make_wav_bytes(channels=2), level="medium")
        self.assertEqual(res.status_code, 200)
        params, _samples = parse_wav(res.data)
        self.assertEqual(params["channels"], 2)
        self.assertEqual(params["rate"], 8000)

    def test_reject_non_wav(self):
        res = self.post_wav(b"this is not a wav file", filename="note.wav")
        self.assertEqual(res.status_code, 400)
        self.assertIn("読み込めませんでした", res.get_data(as_text=True))

    def test_reject_wrong_extension(self):
        res = self.post_wav(make_wav_bytes(), filename="song.mp3")
        self.assertEqual(res.status_code, 400)

    def test_reject_8bit_wav(self):
        res = self.post_wav(make_wav_bytes(sampwidth=1))
        self.assertEqual(res.status_code, 400)
        self.assertIn("16bit", res.get_data(as_text=True))

    def test_missing_file(self):
        res = self.client.post(
            "/convert", data={"level": "weak"}, content_type="multipart/form-data"
        )
        self.assertEqual(res.status_code, 400)


if __name__ == "__main__":
    unittest.main()
