"""Loudness mastering (src/master.py): the finished Short lands on YouTube's
-14 LUFS, measured, with one constant gain (the drop keeps its punch) and the
peaks under the ceiling. Off unless the style pack sets REEL_MASTER_LUFS."""
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import master  # noqa: E402

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


def _short(path: Path, volume: float, seconds: float = 10.0) -> Path:
    """A 10 s stand-in Short: a picture, and a voice-like tone over a quieter bed."""
    subprocess.run([
        "ffmpeg", "-y", "-v", "error",
        "-f", "lavfi", "-i", f"color=c=gray:s=320x568:d={seconds}:r=30",
        "-f", "lavfi", "-i", f"sine=f=220:d={seconds}",
        "-f", "lavfi", "-i", f"anoisesrc=d={seconds}:c=pink:a=0.05",
        "-filter_complex", f"[1:a]volume={volume}[v];[2:a]volume={volume}[n];[v][n]amix=inputs=2:normalize=0[a]",
        "-map", "0:v", "-map", "[a]", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest",
        str(path)], check=True)
    return path


def test_a_quiet_short_comes_up_to_minus_14(tmp_path):
    f = _short(tmp_path / "quiet.mp4", 1.0)
    before, _ = master.measure(f)
    assert before < -17
    r = master.master(f)
    after, peak = master.measure(f)
    assert abs(after - master.TARGET) <= master.TOLERANCE + 0.2, r
    assert peak <= -0.8, r                                   # true peak stays under -1 dBTP or so
    assert r["gain"] > 3


def test_the_picture_is_copied_not_re_encoded(tmp_path):
    f = _short(tmp_path / "v.mp4", 1.0)
    def frames(p):
        return subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                               "stream=codec_name,width,height,nb_frames", "-of", "csv=p=0", str(p)],
                              capture_output=True, text=True).stdout.strip()
    before = frames(f)
    master.master(f)
    assert frames(f) == before


def test_on_target_files_and_broken_files_are_left_alone(tmp_path):
    f = _short(tmp_path / "ok.mp4", 1.0)
    master.master(f)
    size = f.stat().st_size
    assert master.master(f).get("skipped") == "already on target"
    assert f.stat().st_size == size
    junk = tmp_path / "junk.mp4"
    junk.write_bytes(b"not a video")
    r = master.master(junk)
    assert "error" in r and junk.read_bytes() == b"not a video"


def test_off_unless_the_pack_asks(monkeypatch):
    monkeypatch.delenv("REEL_MASTER_LUFS", raising=False)
    assert master.target_from_env() is None
    monkeypatch.setenv("REEL_MASTER_LUFS", "-14")
    assert master.target_from_env() == -14.0
    monkeypatch.setenv("REEL_MASTER_LUFS", "loud")
    assert master.target_from_env() is None
    src = (ROOT / "scripts" / "daily_post.py").read_text(encoding="utf-8")
    assert "target = master_mod.target_from_env()" in src
