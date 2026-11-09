FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY proveedor_pago.py .
RUN useradd --no-create-home servicio
USER servicio
EXPOSE 9500
CMD ["uvicorn", "proveedor_pago:app", "--host", "0.0.0.0", "--port", "9500"]
