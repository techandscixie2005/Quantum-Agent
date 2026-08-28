FROM python:3.12-slim
RUN useradd --uid 10001 --create-home runner
WORKDIR /app
COPY services/api/pyproject.toml /app/pyproject.toml
COPY services/api/quantum_agent /app/quantum_agent
RUN pip install --no-cache-dir fastapi uvicorn pydantic pydantic-settings httpx numpy scipy
USER 10001:10001
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
