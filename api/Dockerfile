FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt


COPY app/ ./app/
COPY ingestion/ ./ingestion/
COPY tools/ ./tools/
COPY tests/ ./tests
COPY evaluate_with_ontology.py .
COPY evaluate_with_ontology_robust.py .
COPY llm_as_judge_test.py .
RUN mkdir -p logs docs

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
