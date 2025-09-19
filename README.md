conda create -n pdf_toolkit python=3.11 -y

conda activate pdf_toolkit

pip install -r requirements.txt

python experiment.

uvicorn pdf_api:app --host 0.0.0.0 --port 8000

Swagger UI: http://localhost:8000/docs
ReDoc: http://localhost:8000/redoc