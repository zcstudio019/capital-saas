bind = "0.0.0.0:8001"
worker_class = "uvicorn.workers.UvicornWorker"
workers = 2
timeout = 120
accesslog = "-"
errorlog = "-"
capture_output = True

