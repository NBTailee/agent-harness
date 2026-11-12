
FROM python:3.12-slim

# --------------------------------------------------
# 2. Environment configuration
# --------------------------------------------------
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# --------------------------------------------------
# 3. Install system dependencies
# --------------------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
    bash \
    coreutils \
    git \
    && rm -rf /var/lib/apt/lists/*

# --------------------------------------------------
# 4. Create a non-root user
# --------------------------------------------------
RUN groupadd --gid 10001 agent && \
    useradd --uid 10001 --gid agent --create-home agent

# --------------------------------------------------
# 5. Create workspace
# --------------------------------------------------
RUN mkdir -p /workspace && \
    chown -R agent:agent /workspace

WORKDIR /workspace

# --------------------------------------------------
# 6. Install Python dependencies
# --------------------------------------------------
COPY requirements.txt /tmp/requirements.txt

RUN if [ -s /tmp/requirements.txt ]; then \
        pip install --no-cache-dir -r /tmp/requirements.txt; \
    fi && \
    rm /tmp/requirements.txt

# --------------------------------------------------
# 7. Switch to non-root user
# --------------------------------------------------
USER 10001:10001

# --------------------------------------------------
# 8. Default container command
# --------------------------------------------------
CMD ["sleep", "infinity"]
