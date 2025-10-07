FROM python:3.10-slim

WORKDIR /app

RUN apt update

RUN apt -y install tshark file binutils curl

# Install dependencies
RUN pip install --no-cache-dir "mcp[cli]"
RUN pip install --no-cache-dir "requests"

# Ensure Python output is unbuffered so logs stream immediately
ENV PYTHONUNBUFFERED=1

# Copy the server code
COPY server.py /app/

# Create a directory to mount the local files
RUN mkdir /data

# Command to run the server
CMD ["python", "server.py"]
