from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi import Request
import subprocess
import uuid
import os

app = FastAPI()

# Dossiers
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
    target_format: str = Form(...)
):
    # Nom de fichier temporaire
    input_id = str(uuid.uuid4())
    output_id = str(uuid.uuid4())

    input_path = os.path.join(UPLOAD_DIR, f"{input_id}_{file.filename}")
    output_filename = f"{output_id}.{target_format}"
    output_path = os.path.join(OUTPUT_DIR, output_filename)

    # Sauvegarder le fichier uploadé
    with open(input_path, "wb") as f:
        content = await file.read()
        f.write(content)

    # Construire la commande ffmpeg
    # Exemple : ffmpeg -i input.mp4 output.mp3
    cmd = [
        "ffmpeg",
        "-y",
        "-i", input_path,
        output_path
    ]

    # Lancer la conversion
    subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    # On pourrait supprimer le fichier d'entrée après
    # os.remove(input_path)

    return FileResponse(
        output_path,
        media_type="application/octet-stream",
        filename=output_filename
    )
