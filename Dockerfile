FROM python:3.10
ENV VENV_PATH="/venv"
ENV PATH="$VENV_PATH/bin:$PATH"
WORKDIR /app
RUN apt-get update && \
    apt-get install -y --no-install-recommends apt-utils && \
    apt-get upgrade -y && \
    apt-get install ffmpeg tesseract-ocr -y && \
    apt-get autoclean
RUN pip install --upgrade poetry
RUN python -m venv /venv
COPY . .
RUN poetry build && \
    /venv/bin/pip install --upgrade pip wheel setuptools &&\
    /venv/bin/pip install dist/*.whl
EXPOSE 8080
ENV SERVICE_URL=http://localhost:8081
# Run Streamlit on port 8080 (primary port) and health server on 8081
CMD ["/bin/sh", "-c", "tgcf-web --server.port=8080 & python health_server.py & python keep_alive.py"]
