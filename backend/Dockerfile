FROM python:3.12-slim

WORKDIR /app
COPY backend/pyproject.toml backend/requirements.txt ./backend/
RUN pip install --no-cache-dir -e "./backend[dev]"
COPY backend/src ./backend/src

ENV PYTHONPATH=/app/backend/src
EXPOSE 8000
CMD ["uvicorn", "projectlens.api:app", "--host", "0.0.0.0", "--port", "8000"]
