FROM python:3.12
WORKDIR /app
COPY . /app
RUN pip install .
EXPOSE 8000
CMD ["sh", "scripts/start_service.sh"]
