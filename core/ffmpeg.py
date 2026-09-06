import json
import shutil
import subprocess
from pathlib import Path

VIDEO_AUDIO_EXTENSIONS = {
    ".mp4", ".mkv", ".avi", ".mov", ".webm", ".wmv", ".flv", ".mpeg",
    ".mpg", ".m4v", ".3gp", ".ts", ".mts", ".m2ts", ".ogv", ".vob",
    ".mp3", ".wav", ".flac", ".aac", ".m4a", ".ogg", ".opus", ".wma",
    ".aiff", ".aif", ".amr", ".alac", ".ac3", ".dts"
}

def find_binary(name: str):
    return shutil.which(name)

def ffmpeg_available():
    return bool(find_binary("ffmpeg") and find_binary("ffprobe"))

def probe(path: str):
    if not ffmpeg_available():
        raise RuntimeError("FFmpeg and ffprobe were not found on PATH.")

    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries",
        "format=duration,size,format_name:stream=index,codec_type,codec_name,sample_rate,channels,width,height",
        "-of", "json", path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Unable to inspect the media file.")

    data = json.loads(result.stdout or "{}")
    fmt = data.get("format", {})
    streams = data.get("streams", [])
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    video = next((s for s in streams if s.get("codec_type") == "video"), None)

    duration = float(fmt.get("duration") or 0)
    size = int(float(fmt.get("size") or 0))

    return {
        "duration": duration,
        "size": size,
        "format": fmt.get("format_name", "Unknown"),
        "audio": audio or {},
        "video": video or {},
        "streams": streams,
    }

def build_command(input_path, output_path, output_format, start=None, end=None,
                  bitrate="192k", sample_rate="44100", channels="2", bit_depth="16",
                  compression="5"):
    cmd = ["ffmpeg", "-hide_banner", "-y"]

    if start is not None and start > 0:
        cmd += ["-ss", str(start)]

    cmd += ["-i", input_path]

    if end is not None and start is not None and end > start:
        cmd += ["-t", str(end - start)]

    cmd += ["-vn"]

    if output_format == "mp3":
        cmd += ["-c:a", "libmp3lame", "-b:a", bitrate, "-ar", sample_rate, "-ac", channels]
    elif output_format == "wav":
        codec = {"16": "pcm_s16le", "24": "pcm_s24le", "32": "pcm_s32le"}.get(bit_depth, "pcm_s16le")
        cmd += ["-c:a", codec, "-ar", sample_rate, "-ac", channels]
    elif output_format == "flac":
        cmd += ["-c:a", "flac", "-compression_level", compression, "-ar", sample_rate, "-ac", channels]
    elif output_format == "aac":
        cmd += ["-c:a", "aac", "-b:a", bitrate, "-ar", sample_rate, "-ac", channels]
    elif output_format == "m4a":
        cmd += ["-c:a", "aac", "-b:a", bitrate, "-ar", sample_rate, "-ac", channels]
    elif output_format == "ogg":
        cmd += ["-c:a", "libvorbis", "-b:a", bitrate, "-ar", sample_rate, "-ac", channels]
    elif output_format == "opus":
        cmd += ["-c:a", "libopus", "-b:a", bitrate, "-ar", sample_rate, "-ac", channels]
    elif output_format == "aiff":
        codec = {"16": "pcm_s16be", "24": "pcm_s24be", "32": "pcm_s32be"}.get(bit_depth, "pcm_s16be")
        cmd += ["-c:a", codec, "-ar", sample_rate, "-ac", channels]
    else:
        raise ValueError(f"Unsupported output format: {output_format}")

    cmd += [output_path]
    return cmd

def parse_progress_time(line: str):
    marker = "out_time_ms="
    if marker in line:
        try:
            return int(line.split(marker, 1)[1].strip()) / 1_000_000
        except ValueError:
            return None
    return None


def build_edit_command(input_path, output_path, output_format,
                       start=0, end=None, volume=100,
                       fade_in=0, fade_out=0, speed=1.0,
                       normalize=False, bitrate="192k"):
    """Build an FFmpeg command for destructive audio editing/export."""
    cmd = ["ffmpeg", "-hide_banner", "-y", "-ss", str(max(0, start)), "-i", input_path]

    filters = []

    vol = max(0.0, float(volume) / 100.0)
    if abs(vol - 1.0) > 0.0001:
        filters.append(f"volume={vol:.4f}")

    if speed and abs(float(speed) - 1.0) > 0.0001:
        # atempo accepts 0.5..2.0 per filter. Chain it for wider ranges.
        value = float(speed)
        while value > 2.0:
            filters.append("atempo=2.0")
            value /= 2.0
        while value < 0.5:
            filters.append("atempo=0.5")
            value /= 0.5
        filters.append(f"atempo={value:.6f}")

    if fade_in > 0:
        filters.append(f"afade=t=in:st=0:d={float(fade_in):.3f}")

    if fade_out > 0 and end is not None:
        edited_duration = max(0.0, float(end) - float(start))
        fade_start = max(0.0, edited_duration - float(fade_out))
        filters.append(f"afade=t=out:st={fade_start:.3f}:d={float(fade_out):.3f}")

    if normalize:
        filters.append("loudnorm=I=-16:TP=-1.5:LRA=11")

    if filters:
        cmd += ["-af", ",".join(filters)]

    if end is not None and float(end) > float(start):
        cmd += ["-t", str(float(end) - float(start))]

    fmt = output_format.lower()
    if fmt == "mp3":
        cmd += ["-c:a", "libmp3lame", "-b:a", bitrate]
    elif fmt == "wav":
        cmd += ["-c:a", "pcm_s16le"]
    elif fmt == "flac":
        cmd += ["-c:a", "flac"]
    elif fmt == "m4a":
        cmd += ["-c:a", "aac", "-b:a", bitrate]
    elif fmt == "aac":
        cmd += ["-c:a", "aac", "-b:a", bitrate]
    elif fmt == "ogg":
        cmd += ["-c:a", "libvorbis", "-b:a", bitrate]
    elif fmt == "opus":
        cmd += ["-c:a", "libopus", "-b:a", bitrate]
    elif fmt == "aiff":
        cmd += ["-c:a", "pcm_s16be"]
    else:
        raise ValueError(f"Unsupported output format: {output_format}")

    cmd += ["-vn", output_path]
    return cmd


def build_mixer_command(tracks, output_path, output_format="mp3",
                        bitrate="192k", normalize=False):
    """Mix timeline-positioned audio tracks using FFmpeg."""
    active = [t for t in tracks if not t.get("mute", False)]
    if not active:
        raise ValueError("There are no unmuted mixer tracks.")

    cmd = ["ffmpeg", "-hide_banner", "-y"]

    for track in active:
        cmd += ["-i", track["path"]]

    filters = []
    labels = []

    for i, track in enumerate(active):
        source_start = max(0.0, float(track.get("source_start", 0)))
        source_end = float(track.get("source_end", track.get("duration", 0)))
        if source_end <= source_start:
            source_end = source_start + max(0.01, float(track.get("duration", 0)))

        timeline_start = max(0.0, float(track.get("timeline_start", 0)))
        fade_in = max(0.0, float(track.get("fade_in", 0)))
        fade_out = max(0.0, float(track.get("fade_out", 0)))
        clip_duration = max(0.01, source_end - source_start)

        fade_in = min(fade_in, clip_duration)
        fade_out = min(fade_out, clip_duration)

        vol = max(0.0, float(track.get("volume", 100)) / 100.0)
        pan = max(-1.0, min(1.0, float(track.get("pan", 0))))
        left = (1.0 - pan) / 2.0
        right = (1.0 + pan) / 2.0

        label = f"a{i}"
        chain = (
            f"[{i}:a]"
            f"atrim=start={source_start:.3f}:end={source_end:.3f},"
            f"asetpts=PTS-STARTPTS"
        )

        if fade_in > 0:
            chain += f",afade=t=in:st=0:d={fade_in:.3f}"
        if fade_out > 0:
            fade_start = max(0.0, clip_duration - fade_out)
            chain += f",afade=t=out:st={fade_start:.3f}:d={fade_out:.3f}"

        chain += (
            f",volume={vol:.4f},"
            f"pan=stereo|c0={left:.4f}*c0+{right:.4f}*c1|"
            f"c1={right:.4f}*c0+{left:.4f}*c1"
        )

        # Place the edited clip on the shared mixer timeline.
        delay_ms = int(round(timeline_start * 1000))
        chain += f",adelay={delay_ms}|{delay_ms}[{label}]"

        filters.append(chain)
        labels.append(f"[{label}]")

    mix = "".join(labels)
    filters.append(
        f"{mix}amix=inputs={len(labels)}:duration=longest:"
        f"dropout_transition=0"
    )

    if normalize:
        filters[-1] += ",loudnorm=I=-16:TP=-1.5:LRA=11"

    filters[-1] += "[out]"
    cmd += [
        "-filter_complex", ";".join(filters),
        "-map", "[out]",
    ]

    fmt = output_format.lower()
    if fmt == "mp3":
        cmd += ["-c:a", "libmp3lame", "-b:a", bitrate]
    elif fmt == "wav":
        cmd += ["-c:a", "pcm_s16le"]
    elif fmt == "flac":
        cmd += ["-c:a", "flac"]
    elif fmt == "m4a":
        cmd += ["-c:a", "aac", "-b:a", bitrate]
    elif fmt == "aac":
        cmd += ["-c:a", "aac", "-b:a", bitrate]
    elif fmt == "ogg":
        cmd += ["-c:a", "libvorbis", "-b:a", bitrate]
    elif fmt == "opus":
        cmd += ["-c:a", "libopus", "-b:a", bitrate]
    elif fmt == "aiff":
        cmd += ["-c:a", "pcm_s16be"]
    else:
        raise ValueError(f"Unsupported output format: {output_format}")

    cmd += ["-vn", output_path]
    return cmd

