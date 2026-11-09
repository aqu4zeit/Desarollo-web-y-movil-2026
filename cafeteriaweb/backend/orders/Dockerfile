FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY orders.py .
RUN useradd --no-create-home servicio
USER servicio
EXPOSE 9200
CMD ["uvicorn", "orders:app", "--host", "0.0.0.0", "--port", "9200"]
