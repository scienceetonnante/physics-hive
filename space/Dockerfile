# The PhysicsHive Space (a Docker Space: see README.md). The app listens on port 7860.
# git reads the workspace and its history; latexmk and TeX Live compile the draft and the notes to PDF.
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
        git latexmk texlive-latex-base texlive-latex-recommended texlive-fonts-recommended \
    && rm -rf /var/lib/apt/lists/*
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user PATH=/home/user/.local/bin:$PATH PYTHONUNBUFFERED=1
WORKDIR $HOME/app
COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt
COPY --chown=user . .
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7860", "--proxy-headers", "--forwarded-allow-ips", "*"]
