FROM python:3.12-slim

WORKDIR /app

# Non-root runtime user; uid 1000 matches the host owner of ./data
RUN useradd -m -u 1000 appuser

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p data && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

CMD ["python", "-m", "app.main"]
