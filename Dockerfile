FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    AUDIT_LOG_FILE="" \
    PORT=8080

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY banking_agent/ banking_agent/
COPY main.py web_guard.py ./

RUN useradd --create-home appuser
USER appuser

EXPOSE 8080
CMD ["python", "main.py"]
