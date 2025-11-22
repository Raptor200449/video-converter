from fastapi import FastAPI, UploadFile, File, Form, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
import subprocess
import uuid
import os

app = FastAPI()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
OUTPUT_DIR = os.path.join(BASE_DIR, "outputs")

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

templates = Jinja2Templates(directory="templates")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/convert")
async def convert_file(
    request: Request,
    file: UploadFile = File(...),
    target_format: str = Form(...),
    quality: str = Form("standard"),
    operation: str = Form("convert"),
    start_time: str = Form("", description="Start time in seconds (for gif/cut)"),
    end_time: str = Form("", description="End time in seconds (for cut)"),
    duration: str = Form("", description="Duration in seconds (for gif)"),
):
    """
    operation :
      - convert  : conversion simple
      - compress : conversion orientée poids réduit
      - audio    : extraire uniquement l'audio
      - gif      : créer un GIF (start_time + duration)
      - cut      : couper un extrait (start_time + end_time)
    """
    input_id = str(uuid.uuid4())
    output_id = str(uuid.uuid4())

    input_path = os.path.join(UPLOAD_DIR, f"{input_id}_{file.filename}")

    # Forcer le format de sortie pour certains modes
    if operation == "gif":
        output_ext = "gif"
    else:
        output_ext = target_format.lower()

    output_filename = f"{output_id}.{output_ext}"
    output_path = os.path.join(OUTPUT_DIR, output_filename)

    # Sauvegarder le fichier uploadé
    with open(input_path, "wb") as f:
        content = await file.read()
        f.write(content)

    # Normaliser les champs temps (vides -> None)
    start_time = (start_time or "").strip() or None
    end_time = (end_time or "").strip() or None
    duration = (duration or "").strip() or None

    video_formats = {"mp4", "mkv", "mov"}

    # Construire la commande ffmpeg selon l'opération
    if operation == "gif":
        # GIF animé, fps réduit + scale pour limiter le poids
        cmd = ["ffmpeg", "-y"]
        if start_time:
            cmd += ["-ss", start_time]
        if duration:
            cmd += ["-t", duration]
        cmd += [
            "-i",
            input_path,
            "-vf",
            "fps=12,scale=640:-1:flags=lanczos",
            "-loop",
            "0",
            output_path,
        ]

    elif operation == "cut":
        cmd = ["ffmpeg", "-y"]
        if start_time:
            cmd += ["-ss", start_time]
        if end_time:
            cmd += ["-to", end_time]
        cmd += ["-i", input_path, output_path]

    elif operation == "audio":
        # Forcer un format audio cohérent si nécessaire
        if output_ext not in {"mp3", "wav"}:
            output_ext = "mp3"
            output_filename = f"{output_id}.{output_ext}"
            output_path = os.path.join(OUTPUT_DIR, output_filename)
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            input_path,
            "-vn",  # no video
            output_path,
        ]

    else:
        # convert / compress par défaut, avec gestion de la qualité vidéo
        cmd = ["ffmpeg", "-y", "-i", input_path]

        if output_ext in video_formats:
            if quality == "light":
                cmd += ["-vcodec", "libx264", "-crf", "26"]
            elif quality == "strong":
                cmd += ["-vcodec", "libx264", "-crf", "30"]

        cmd.append(output_path)

    # Lancer la conversion
    process = subprocess.run(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    # Si besoin de debug : print(process.stderr)

    return FileResponse(
        output_path,
        media_type="application/octet-stream",
        filename=output_filename,
    )
