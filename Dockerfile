FROM python:3.11-slim
WORKDIR /app
COPY portal/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY portal/ .
CMD ["python", "app.py"]
