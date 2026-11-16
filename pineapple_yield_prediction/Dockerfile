FROM python:3.12-slim

WORKDIR /app

COPY requirements-serve.txt .
RUN pip install --no-cache-dir -r requirements-serve.txt

COPY predict.py ./
COPY model/pineapple_yield_model.joblib ./model/

EXPOSE 9696

CMD ["uvicorn", "predict:app", "--host", "0.0.0.0", "--port", "9696"]
