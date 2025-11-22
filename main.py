import os
import uuid
import subprocess
from pathlib import Path

from flask import Flask, render_template, request, send_file, abort

app = Flask(__name__)

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "outputs"

UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)


def build_ffmpeg_command(
    input_path: Path,
    output_path: Path,
    operation: str,
    target_format: str,
    quality: str,
    start_time: str | None = None,
    duration: str | None = None,
    end_time: str | None = None,
    resolution: str | None = None,
    fps: str | None = None,
    audio_bitrate: str | None = None,
):
    cmd = ["ffmpeg", "-y"]

    # Découpage (ss / t / to)
    if start_time:
        cmd.extend(["-ss", start_time])

    cmd.extend(["-i", str(input_path)])

    if operation == "audio":
        # Audio uniquement
        cmd.append("-vn")

    # Profil qualité vidéo
    vcodec = None
    video_flags = []
    if operation in ("convert", "compress", "gif", "cut"):
        # H.264 pour la plupart des sorties vidéo
        vcodec = "libx264"

        if quality == "light":       # plus léger
            video_flags.extend(["-crf", "26", "-preset", "veryfast"])
        elif quality == "strong":    # très compressé
            video_flags.extend(["-crf", "30", "-preset", "faster"])
        else:                        # standard
            video_flags.extend(["-crf", "23", "-preset", "medium"])

    # Résolution & FPS (pour la vidéo / GIF)
    vf_parts = []
    if resolution and resolution != "source":
        # scale=-2:hauteur pour garder le ratio
        if resolution == "480p":
            vf_parts.append("scale=-2:480")
        elif resolution == "720p":
            vf_parts.append("scale=-2:720")
        elif resolution == "1080p":
            vf_parts.append("scale=-2:1080")

    if fps and fps != "source":
        vf_parts.append(f"fps={fps}")

    if vf_parts and operation != "audio":
        video_flags.extend(["-vf", ",".join(vf_parts)])

    # Bitrate audio
    audio_flags = []
    if audio_bitrate and audio_bitrate != "auto":
        audio_flags.extend(["-b:a", audio_bitrate])

    # Découpage durée
    if duration:
        video_flags.extend(["-t", duration])
    elif end_time and start_time:
        # -to = temps absolu depuis le début
        video_flags.extend(["-to", end_time])

    # Opération GIF spécifique
    if operation == "gif":
        # Palette pour GIF un peu plus propres
        # On reste simple pour l’instant
        output_path = output_path.with_suffix(".gif")
        target_format = "gif"
        vcodec = None  # ffmpeg choisira

    # Construction finale des flags codecs
    if vcodec and operation != "audio":
        cmd.extend(["-c:v", vcodec])

    if audio_flags and operation != "gif":
        cmd.extend(audio_flags)

    # Ajout flags vidéo si présents
    cmd.extend(video_flags)

    # Format audio-only (mp3/wav/flac etc.)
    if operation == "audio":
        # Laisser ffmpeg choisir le codec selon l’extension
        pass

    cmd.append(str(output_path))
    return cmd, output_path


@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")


@app.route("/convert", methods=["POST"])
def convert():
    if "file" not in request.files:
        abort(400, "Aucun fichier reçu")

    file = request.files["file"]
    if file.filename == "":
        abort(400, "Fichier vide")

    # Champs principaux
    operation = request.form.get("operation", "convert")
    target_format = request.form.get("target_format", "mp4").lower()
    quality = request.form.get("quality", "standard")

    # Options temps
    start_time = request.form.get("start_time") or None
    duration = request.form.get("duration") or None
    end_time = request.form.get("end_time") or None

    # Options avancées
    resolution = request.form.get("resolution") or "source"
    fps = request.form.get("fps") or "source"
    audio_bitrate = request.form.get("audio_bitrate") or "auto"

    # Sauvegarde du fichier uploadé
    input_ext = Path(file.filename).suffix or f".{target_format}"
    input_name = f"{uuid.uuid4().hex}{input_ext}"
    input_path = UPLOAD_DIR / input_name
    file.save(input_path)

    # Chemin de sortie
    if operation == "gif":
        output_ext = ".gif"
    elif operation == "audio":
        output_ext = f".{target_format}"
    else:
        output_ext = f".{target_format}"

    output_name = f"{uuid.uuid4().hex}{output_ext}"
    output_path = OUTPUT_DIR / output_name

    try:
        cmd, final_output_path = build_ffmpeg_command(
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
        )

        # Exécution ffmpeg
        completed = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        if completed.returncode != 0 or not final_output_path.exists():
            print("FFmpeg error:", completed.stderr)
            abort(500, "Erreur pendant la conversion / compression du fichier.")

        # Téléchargement
        return send_file(
            final_output_path,
            as_attachment=True,
            download_name=final_output_path.name,
        )

    finally:
        # Nettoyage basique : on garde seulement les outputs
        try:
            if input_path.exists():
                input_path.unlink()
        except Exception:
            pass


if __name__ == "__main__":
    app.run(debug=True)
