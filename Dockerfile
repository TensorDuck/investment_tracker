# Use the official lightweight Python image.
# https://hub.docker.com/_/python
FROM python:3.8-slim

# Pass in the AV API Key
ARG AV_API_KEY
ENV AV_API_KEY=$AV_API_KEY
# Allow statements and log messages to immediately appear in the Knative logs
ENV PYTHONUNBUFFERED True

# Copy local code to the container image.
ENV APP_HOME /app
WORKDIR $APP_HOME
COPY investment_tracker/ /app/investment_tracker
COPY requirements-gcp.txt /app/requirements-gcp.txt

# Install production dependencies.
RUN pip install Flask gunicorn
RUN pip install -r requirements-gcp.txt

# Run the web service on container startup. Here we use the gunicorn
# webserver, with one worker process and 8 threads.
# For environments with multiple CPU cores, increase the number of workers
# to be equal to the cores available.
CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 investment_tracker.gcp_deploy.app:app
