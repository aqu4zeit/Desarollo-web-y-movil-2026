FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY auth.py .
RUN useradd --no-create-home servicio
USER servicio
EXPOSE 8100
CMD ["uvicorn", "auth:app", "--host", "0.0.0.0", "--port", "8100"]
