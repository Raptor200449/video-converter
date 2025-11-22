import uuid
import subprocess
from pathlib import Path
from mimetypes import guess_type

from flask import (
    Flask,
    render_template,
    request,
    send_file,
    abort,
    redirect,
    url_for,
)

app = Flask(__name__)

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "outputs"

UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)


def run_ffmpeg(cmd: list[bytes | str]) -> subprocess.CompletedProcess:
    """Lance ffmpeg et renvoie le CompletedProcess (log utile en cas de bug)."""
    return subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def build_video_command(
    input_path: Path,
    output_path: Path,
    operation: str,
    target_format: str,
    quality: str,
    start_time: str | None,
    duration: str | None,
    end_time: str | None,
    resolution: str,
    fps: str,
    audio_bitrate: str,
    speed: str,
    reverse: bool,
    audio_only: bool = False,
    gif_mode: bool = False,
) -> list[str]:
    """
    Construit la commande ffmpeg pour tous les cas sauf merge.
    audio_only = True -> extrait / convertit uniquement l'audio.
    gif_mode = True   -> sort un .gif (même si target_format autre).
    """
    cmd: list[str] = ["ffmpeg", "-y"]

    # Start time (-ss avant -i pour couper plus vite)
    if start_time:
        cmd.extend(["-ss", start_time])

    cmd.extend(["-i", str(input_path)])

    # Si audio_only, on coupe la vidéo
    if audio_only:
        cmd.append("-vn")

    # Gestion de la vitesse
    try:
        speed_value = float(speed) if speed else 1.0
    except ValueError:
        speed_value = 1.0

    # Filtres vidéo
    vf_parts = []
    if resolution and resolution != "source" and not audio_only and not gif_mode:
        if resolution == "480p":
            vf_parts.append("scale=-2:480")
        elif resolution == "720p":
            vf_parts.append("scale=-2:720")
        elif resolution == "1080p":
            vf_parts.append("scale=-2:1080")

    if fps and fps != "source" and not audio_only:
        vf_parts.append(f"fps={fps}")

    if speed_value != 1.0 and not audio_only:
        vf_parts.append(f"setpts=PTS/{speed_value}")

    if reverse and not audio_only:
        vf_parts.append("reverse")

    # Filtres audio
    af_parts = []
    if speed_value != 1.0:
        af_parts.append(f"atempo={speed_value}")
    if reverse:
        af_parts.append("areverse")

    # Qualité vidéo / codec
    if gif_mode:
        # On sort un GIF
        output_path = output_path.with_suffix(".gif")
    vcodec = None
    if not audio_only and not gif_mode:
        vcodec = "libx264"

    video_flags: list[str] = []
    if vcodec:
        video_flags.extend(["-c:v", vcodec])
        if quality == "light":
            video_flags.extend(["-crf", "26", "-preset", "fast"])
        elif quality == "strong":
            video_flags.extend(["-crf", "30", "-preset", "faster"])
        else:
            video_flags.extend(["-crf", "23", "-preset", "medium"])

    # VF final
    if vf_parts and not audio_only:
        video_flags.extend(["-vf", ",".join(vf_parts)])

    # Audio bitrate
    audio_flags: list[str] = []
    if audio_bitrate and audio_bitrate != "auto" and not gif_mode:
        audio_flags.extend(["-b:a", audio_bitrate])

    # AF final
    if af_parts and not gif_mode:
        audio_flags.extend(["-filter:a", ",".join(af_parts)])

    # Cut
    if duration:
        video_flags.extend(["-t", duration])
    elif end_time and start_time and not duration:
        # ffmpeg accepte -to avec -ss
        video_flags.extend(["-to", end_time])

    # Construction finale
    cmd.extend(video_flags)
    cmd.extend(audio_flags)

    # Format de sortie (sauf GIF qui a forcé l'extension)
    if gif_mode:
        output_real = output_path.with_suffix(".gif")
    else:
        output_real = output_path.with_suffix(f".{target_format.lstrip('.')}")

    cmd.append(str(output_real))
    return cmd, output_real


@app.route("/")
def index():
    # Page principale sans preset
    return render_template("index.html", preset_mode="", preset_format="")


@app.route("/convertir-mp4-en-mp3")
def convertir_mp4_mp3():
    # Page SEO : pré-config MP4 -> MP3
    return render_template("index.html", preset_mode="audio", preset_format="mp3")


@app.route("/result/<filename>")
def result(filename: str):
    path = OUTPUT_DIR / filename
    if not path.exists():
        abort(404)

    ext = path.suffix.lower()
    if ext in {".mp4", ".mov", ".mkv"}:
        kind = "video"
    elif ext in {".mp3", ".wav", ".aac", ".flac"}:
        kind = "audio"
    elif ext == ".gif":
        kind = "gif"
    else:
        kind = "other"

    size_mb = path.stat().st_size / 1024 / 1024
    return render_template("result.html", filename=filename, kind=kind, size_mb=size_mb)


@app.route("/file/<filename>")
def file_preview(filename: str):
    path = OUTPUT_DIR / filename
    if not path.exists():
        abort(404)
    mime, _ = guess_type(str(path))
    return send_file(path, mimetype=mime or "application/octet-stream")


@app.route("/download/<filename>")
def download(filename: str):
    path = OUTPUT_DIR / filename
    if not path.exists():
        abort(404)
    return send_file(path, as_attachment=True, download_name=filename)


@app.route("/convert", methods=["POST"])
def convert():
    # Fichier principal obligatoire
    if "file" not in request.files:
        abort(400, "Aucun fichier fourni.")
    file = request.files["file"]
    if not file or file.filename == "":
        abort(400, "Aucun fichier sélectionné.")

    operation = request.form.get("operation", "convert")
    target_format = (request.form.get("target_format") or "mp4").lower()
    quality = request.form.get("quality", "standard")

    start_time = request.form.get("start_time") or None
    duration = request.form.get("duration") or None
    end_time = request.form.get("end_time") or None

    resolution = request.form.get("resolution") or "source"
    fps = request.form.get("fps") or "source"
    audio_bitrate = request.form.get("audio_bitrate") or "auto"
    speed = request.form.get("speed") or "1.0"
    reverse = request.form.get("reverse") == "on"

    # Sauvegarde du fichier principal
    in_ext = Path(file.filename).suffix or f".{target_format}"
    input_name = f"{uuid.uuid4().hex}{in_ext}"
    input_path = UPLOAD_DIR / input_name
    file.save(input_path)

    # Fichier de sortie (on ajustera l'extension plus tard)
    output_base = uuid.uuid4().hex
    output_path = OUTPUT_DIR / output_base

    try:
        # CAS MERGE
        if operation == "merge":
            file2 = request.files.get("file2")
            if not file2 or file2.filename == "":
                abort(400, "Deuxième fichier manquant pour la fusion.")

            in2_ext = Path(file2.filename).suffix or f".{target_format}"
            input2_name = f"{uuid.uuid4().hex}{in2_ext}"
            input2_path = UPLOAD_DIR / input2_name
            file2.save(input2_path)

            out_file = output_path.with_suffix(f".{target_format.lstrip('.')}")
            cmd = [
                "ffmpeg",
                "-y",
                "-i",
                str(input_path),
                "-i",
                str(input2_path),
                "-filter_complex",
                "[0:v][0:a][1:v][1:a]concat=n=2:v=1:a=1[v][a]",
                "-map",
                "[v]",
                "-map",
                "[a]",
                "-c:v",
                "libx264",
                "-crf",
                "23",
                "-preset",
                "medium",
                str(out_file),
            ]
            completed = run_ffmpeg(cmd)
            if completed.returncode != 0 or not out_file.exists():
                print("FFmpeg merge error:", completed.stderr)
                abort(500, "Erreur lors de la fusion.")
            # Nettoyage 2e fichier
            try:
                input2_path.unlink()
            except Exception:
                pass

            return redirect(url_for("result", filename=out_file.name))

        # Détermine audio_only / gif_mode
        audio_only = operation == "audio" or target_format in {"mp3", "wav"} and operation != "gif"
        gif_mode = operation == "gif"

        cmd, final_output = build_video_command(
            input_path=input_path,
            output_path=output_path,
            operation=operation,
            target_format=target_format,
            quality=quality,
            start_time=start_time,
            duration=duration,
            end_time=end_time,
            resolution=resolution,
            fps=fps,
            audio_bitrate=audio_bitrate,
            speed=speed,
            reverse=reverse,
            audio_only=audio_only,
            gif_mode=gif_mode,
        )

        completed = run_ffmpeg(cmd)
        if completed.returncode != 0 or not final_output.exists():
            print("FFmpeg error:", completed.stderr)
            abort(500, "Erreur pendant la conversion.")

        return redirect(url_for("result", filename=final_output.name))

    finally:
        # Nettoyage du fichier uploadé principal
        try:
            input_path.unlink()
        except Exception:
            pass


if __name__ == "__main__":
    # Pour le local. Sur Render tu utiliseras gunicorn.
    app.run(host="0.0.0.0", port=5000, debug=True)
