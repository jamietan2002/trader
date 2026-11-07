FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV TRADING_MODE=paper
EXPOSE 8080 8501

CMD ["python3", "main.py", "serve", "--host", "0.0.0.0", "--port", "8080"]

