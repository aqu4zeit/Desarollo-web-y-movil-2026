FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY despacho.py .
RUN useradd --no-create-home servicio
USER servicio
EXPOSE 9400
CMD ["uvicorn", "despacho:app", "--host", "0.0.0.0", "--port", "9400"]
