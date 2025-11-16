FROM python:3.12-slim

# Installer ffmpeg
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

# Créer un dossier pour l'app
WORKDIR /app

# Copier les fichiers de dépendances
COPY requirements.txt .

# Installer les libs Python
RUN pip install --no-cache-dir -r requirements.txt

# Copier le reste du projet
COPY . .

# Exposer le port (Uvicorn)
EXPOSE 8000

# Commande de démarrage
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
