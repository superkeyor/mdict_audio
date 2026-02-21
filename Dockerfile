# use a major version of Python for security updates
# https://hub.docker.com/_/python/tags?name=-slim-
# make sure Python Ver. work with Package Ver. in requirements
FROM python:3.11-slim-bookworm
# # PIN python, chromium and driver version
# FROM superkeyor/python_chromium_driver:latest

ENV PYTHONDONTWRITEBYTECODE=1 # no writing .pyc cache files
ENV PYTHONUNBUFFERED=1        # stdout/stderr straight to terminal without buffering delays

# Define env var built into an container image (less flexible than docker-compose.yml)
ENV FLASK_ENV=production
ENV TZ=US/Central

RUN apt-get update && apt-get install -y tzdata && \
    ln -fs /usr/share/zoneinfo/$TZ /etc/localtime && \
    dpkg-reconfigure -f noninteractive tzdata && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# copy requirements first so pip layer is cached unless requirements.txt changes
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt  # --no-cache-dir reduces image size

# copy remaining source files
COPY . .

# Make port available to the world outside this container
# expose from container to host
EXPOSE 5000

# RUN occurs during building; CMD similar to ENTRYPOINT
CMD ["bash", "/app/start.sh"]
