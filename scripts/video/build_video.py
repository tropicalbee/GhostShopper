"""Cut the raw recording into the 11 rows of docs/VIDEO_SCRIPT.md and join them into one mp4.

    python scripts/video/build_video.py --out demo-video/live
    python scripts/video/build_video.py --out demo-video/dry-run --tts

Reads <out>/markers.json (from record_demo.py). Voice clips go in <out>/voice/row01.wav ... row11.wav
(wav, mp3 or m4a). With --tts, rows without a clip get a backup voice from Windows SAPI into <out>/voice-tts/.
Writes <out>/segments/seg01.mp4 ... and <out>/ghostshopper-demo.mp4.
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "docs" / "VIDEO_SCRIPT.md"
FONT = "C\\:/Windows/Fonts/arial.ttf"  # escaped for an ffmpeg filter on Windows
AUDIO_EXT = ("wav", "mp3", "m4a")
TITLE = "GhostShopper"
TAGLINE = "A mystery shopper for the AI agent era"
CARD_SECONDS = 4
VOICE = "Microsoft Zira Desktop"


def secs(t: str) -> int:
    m, s = t.split(":")
    return int(m) * 60 + int(s)


def read_rows() -> list[dict]:
    rows = []
    for line in SCRIPT.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\|\s*(\d+:\d\d)-(\d+:\d\d)\s*\|(.*)\|(.*)\|\s*$", line)
        if m:
            text = m.group(4).strip().strip('"').strip("“”").strip()
            rows.append({"start": secs(m.group(1)), "dur": secs(m.group(2)) - secs(m.group(1)), "voice": text})
    if len(rows) != 11:
        sys.exit(f"Expected 11 rows in {SCRIPT}, found {len(rows)}.")
    return rows


def run(cmd: list[str]):
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        sys.exit(f"Command failed: {' '.join(cmd[:3])} ...\n{r.stderr[-1500:]}")
    return r


def duration(path: Path) -> float:
    r = run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)])
    return float(r.stdout.strip())


def make_tts(rows: list[dict], folder: Path, force: bool):
    folder.mkdir(parents=True, exist_ok=True)
    todo = False
    for i, row in enumerate(rows, 1):
        wav = folder / f"row{i:02d}.wav"
        if force or not wav.exists():
            (folder / f"row{i:02d}.txt").write_text(row["voice"], encoding="utf-8")
            todo = True
    if not todo:
        return
    ps = folder / "make_voice.ps1"
    ps.write_text(
        "param([string]$dir, [string]$voice)\n"
        "Add-Type -AssemblyName System.Speech\n"
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer\n"
        "$s.SelectVoice($voice)\n"
        "$s.Rate = 0\n"
        "foreach ($t in Get-ChildItem -Path $dir -Filter 'row*.txt') {\n"
        "  $wav = [IO.Path]::ChangeExtension($t.FullName, '.wav')\n"
        f"  if ((Test-Path $wav) -and {'$true' if not force else '$false'}) {{ continue }}\n"
        "  $s.SetOutputToWaveFile($wav)\n"
        "  $s.Speak([IO.File]::ReadAllText($t.FullName, [Text.Encoding]::UTF8))\n"
        "  $s.SetOutputToNull()\n"
        "}\n"
        "$s.Dispose()\n",
        encoding="utf-8",
    )
    r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ps), "-dir", str(folder),
                        "-voice", VOICE], capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"SAPI voice generation failed (is '{VOICE}' installed?):\n{r.stderr[-800:]}")


def find_clip(out: Path, i: int) -> Path | None:
    for folder in ("voice", "voice-tts"):
        for ext in AUDIO_EXT:
            p = out / folder / f"row{i:02d}.{ext}"
            if p.exists():
                return p
    return None


def label_filter(factor: float) -> str:
    return (f"drawtext=fontfile='{FONT}':text='{factor:.1f}x':fontsize=44:fontcolor=white:box=1:"
            f"boxcolor=black@0.65:boxborderw=14:x=w-tw-48:y=40")


def card_filter() -> str:
    return (f"drawtext=fontfile='{FONT}':text='{TITLE}':fontsize=110:fontcolor=white:x=(w-tw)/2:y=(h/2)-110,"
            f"drawtext=fontfile='{FONT}':text='{TAGLINE}':fontsize=48:fontcolor=white:x=(w-tw)/2:y=(h/2)+40")


def scene_map(markers: dict) -> dict[str, tuple[float, float]]:
    return {s["scene"]: (s["start"], s["end"]) for s in markers["scenes"]}


def plan_rows(scenes: dict[str, tuple[float, float]]) -> list[list[dict]]:
    """Each row is a list of parts. clip parts take a scene (from/to as offsets inside it); mode 'fit' speeds the
    footage up to fill `out` seconds, mode 'trim' plays it at 1x and cuts it to `out` seconds."""
    def clip(scene, frm=0.0, to=None, out=None, mode="trim"):
        return {"kind": "clip", "scene": scene, "from": frm, "to": to, "out": out, "mode": mode}

    live_len = scenes["bad_run_live"][1] - scenes["bad_run_live"][0]
    split = 10.0 if live_len >= 16 else live_len * 0.4  # the live view starts at 1x, the rest runs fast
    return [
        [clip("store", out=8)],
        [clip("bad_run_live", 0, split, out=10)],
        [clip("bad_run_live", split, None, out=12, mode="fit")],
        [{"kind": "card", "out": CARD_SECONDS}, clip("landing", out=8)],
        [clip("bad_results", out=23)],
        [clip("bad_fixes", out=10)],
        [clip("admin", out=10)],
        [clip("fixed_run_live", out=25, mode="fit")],
        [clip("fixed_trace", out=25)],
        [clip("compare", out=7), clip("market", out=3)],
        [clip("close", out=10)],
    ]


def build_row(i: int, parts: list[dict], row: dict, raw: Path, scenes, clip_audio: Path | None, out_dir: Path,
              max_extend: float, notes: list[str]) -> Path:
    target = float(row["dur"])
    audio_len = duration(clip_audio) if clip_audio else 0.0
    seg_len = target
    if audio_len > target:
        extend = min(audio_len - target, max_extend)
        seg_len = target + extend
        notes.append(f"row {i:02d}: voice clip is {audio_len:.1f}s, row is {target:.0f}s"
                     + (f"; video extended to {seg_len:.1f}s" if extend else "")
                     + ("; audio cut at the end" if audio_len > seg_len + 0.05 else ""))

    cmd = ["ffmpeg", "-y", "-v", "error"]
    chains, labels, n_in = [], [], 0
    factors = []
    for k, part in enumerate(parts):
        if part["kind"] == "card":
            cmd += ["-f", "lavfi", "-i", f"color=c=black:s=1920x1080:r=30:d={part['out']}"]
            chains.append(f"[{n_in}:v]format=yuv420p,{card_filter()},setsar=1[p{k}]")
            factors.append(None)
        else:
            s0, s1 = scenes[part["scene"]]
            a = s0 + part["from"]
            b = s0 + part["to"] if part["to"] is not None else s1
            b = min(b, s1)
            src = max(0.2, b - a)
            speed = 1.0
            if part["mode"] == "fit":
                speed = max(1.0, src / part["out"])
            else:
                src = min(src, part["out"])
            if speed < 1.05:
                speed = 1.0
            cmd += ["-ss", f"{a:.3f}", "-t", f"{src:.3f}", "-i", str(raw)]
            f = (f"[{n_in}:v]setpts=(PTS-STARTPTS)/{speed:.4f},fps=30,scale=1920:1080:flags=lanczos,setsar=1,"
                 f"format=yuv420p")
            if speed > 1.0:
                f += "," + label_filter(speed)
            chains.append(f + f"[p{k}]")
            factors.append(speed)
        labels.append(f"[p{k}]")
        n_in += 1
    video = "".join(labels) + f"concat=n={len(parts)}:v=1:a=0[cat];[cat]tpad=stop_mode=clone:stop_duration=30," \
                              f"trim=duration={seg_len:.3f},setpts=PTS-STARTPTS[v]"
    if clip_audio:
        cmd += ["-i", str(clip_audio)]
        audio = f"[{n_in}:a]aresample=48000,aformat=channel_layouts=stereo,apad,atrim=duration={seg_len:.3f}[a]"
    else:
        cmd += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
        audio = f"[{n_in}:a]atrim=duration={seg_len:.3f}[a]"
    seg = out_dir / f"seg{i:02d}.mp4"
    cmd += ["-filter_complex", ";".join(chains + [video, audio]), "-map", "[v]", "-map", "[a]",
            "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-r", "30",
            "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-t", f"{seg_len:.3f}", str(seg)]
    run(cmd)
    used = [f"{f:.1f}x" for f in factors if f and f > 1.0]
    print(f"  seg{i:02d}  {duration(seg):6.2f}s  voice={'yes' if clip_audio else 'silent'}"
          + (f"  speed {', '.join(used)}" if used else ""), flush=True)
    return seg


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out", default=str(ROOT / "demo-video"))
    p.add_argument("--tts", action="store_true", help="make backup voice clips with Windows SAPI where none exist")
    p.add_argument("--force-tts", action="store_true", help="regenerate the SAPI clips")
    p.add_argument("--max-extend", type=float, default=1.5,
                   help="a voice clip longer than its row may stretch the row by up to this many seconds")
    args = p.parse_args()

    out = Path(args.out).resolve()
    markers = json.loads((out / "markers.json").read_text())
    raw = Path(markers["video"])
    scenes = scene_map(markers)
    rows = read_rows()
    if args.tts:
        make_tts(rows, out / "voice-tts", args.force_tts)

    seg_dir = out / "segments"
    seg_dir.mkdir(exist_ok=True)
    notes: list[str] = []
    plan = plan_rows(scenes)
    print("Building segments")
    segs = [build_row(i, plan[i - 1], rows[i - 1], raw, scenes, find_clip(out, i), seg_dir, args.max_extend, notes)
            for i in range(1, 12)]

    listing = out / "segments.txt"
    listing.write_text("".join(f"file '{s.as_posix()}'\n" for s in segs), encoding="utf-8")
    final = out / "ghostshopper-demo.mp4"
    run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(listing), "-c", "copy",
         "-movflags", "+faststart", str(final)])
    total = duration(final)
    print(f"\n{final}\nDuration {int(total // 60)}:{total % 60:05.2f} ({total:.1f}s)")
    for n in notes:
        print("NOTE", n)
    if total >= 180:
        print("WARNING: the video is 3:00 or longer.")


if __name__ == "__main__":
    main()
