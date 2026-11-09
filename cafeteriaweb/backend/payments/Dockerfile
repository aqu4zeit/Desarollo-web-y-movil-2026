FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY payments.py .
RUN useradd --no-create-home servicio
USER servicio
EXPOSE 9300
CMD ["uvicorn", "payments:app", "--host", "0.0.0.0", "--port", "9300"]
