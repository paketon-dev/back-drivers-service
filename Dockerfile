FROM python:3.11-slim AS python

WORKDIR /app

COPY ./requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app/

EXPOSE 8072

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8072", "--reload", "--log-level", "debug"]