# Monolithic Docker Image for LiveKit Voice Agent
# Includes: LiveKit Server, Python Agent, Token Server, and React Frontend
# syntax=docker/dockerfile:1

# =============================================================================
# Stage 1: Build React Frontend
# =============================================================================
FROM --platform=linux/amd64 node:20-slim AS frontend-builder

WORKDIR /build

# Copy React app files
COPY react-app/package*.json ./
RUN npm ci

COPY react-app/ ./
RUN npm run build

# =============================================================================
# Stage 2: Final Runtime Image
# =============================================================================
FROM --platform=linux/amd64 debian:bookworm-slim

# Prevent interactive prompts during installation
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PATH="/root/.local/bin:$PATH" \
    UV_SYSTEM_PYTHON=1

# Install system dependencies
RUN apt-get update && apt-get install -y \
    # Python build dependencies
    python3.11 \
    python3-pip \
    python3-dev \
    gcc \
    g++ \
    # Node.js for running React app
    curl \
    # Network utilities for health checks
    netcat-openbsd \
    wget \
    ca-certificates \
    # JSON processor required by LiveKit installer
    jq \
    # Clean up
    && rm -rf /var/lib/apt/lists/*

# Install Node.js 20
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install UV (fast Python package manager) using official installer
RUN curl -LsSf https://astral.sh/uv/install.sh | sh \
    && ln -s /root/.cargo/bin/uv /usr/local/bin/uv

# Download and install LiveKit server binary
RUN wget -q https://github.com/livekit/livekit/releases/download/v1.7.2/livekit_1.7.2_linux_amd64.tar.gz -O /tmp/livekit.tar.gz \
    && tar -xzf /tmp/livekit.tar.gz -C /tmp/ \
    && mv /tmp/livekit-server /usr/local/bin/livekit-server \
    && chmod +x /usr/local/bin/livekit-server \
    && rm /tmp/livekit.tar.gz

# Set working directory
WORKDIR /app

# Copy Python dependency files
COPY pyproject.toml uv.lock* ./

# Install Python dependencies using UV
# First try with uv.lock if it exists, otherwise install from pyproject.toml
RUN if [ -f uv.lock ]; then \
        uv sync --no-dev; \
    else \
        uv pip install --system \
        "livekit-agents[mcp]>=1.2.0" \
        "livekit-plugins-openai>=1.0.0" \
        "livekit-plugins-deepgram>=1.0.0" \
        "livekit-plugins-silero>=1.0.0" \
        "livekit-plugins-turn-detector>=1.0.0" \
        "livekit-agents[cartesia]~=1.2" \
        "python-dotenv>=1.0.0" \
        "inferedge-moss" \
        "flask>=3.0.0" \
        "flask-cors>=4.0.0" \
        "livekit>=0.17.0"; \
    fi

# Copy Python application files
COPY agent.py token_server.py settings.py create_index.py ./
COPY faqs.json* ./

# Copy built React app from builder stage
COPY --from=frontend-builder /build/dist /app/react-app/dist
COPY --from=frontend-builder /build/package*.json /app/react-app/

# Install a simple HTTP server to serve the React app
RUN npm install -g http-server

# Expose all required ports
# 7880: LiveKit signaling (WebSocket)
# 7881: LiveKit RTC over TCP
# 7882: LiveKit RTC over UDP
# 8080: Token server
# 4173: React frontend
EXPOSE 7880 7881 7882/udp 8080 4173

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD netcat -z localhost 7880 && netcat -z localhost 8080 && netcat -z localhost 4173 || exit 1

# Start all services using inline bash
# - LiveKit server runs in background
# - Token server runs in background  
# - Python agent runs in background
# - React app runs in foreground (keeps container alive)
CMD ["/bin/bash", "-c", "\
    set -e; \
    echo '🚀 Starting LiveKit Server...'; \
    livekit-server --dev \
        --bind 0.0.0.0 \
        --node-ip 127.0.0.1 \
        --udp-port 7882 \
        > /var/log/livekit.log 2>&1 & \
    LIVEKIT_PID=$!; \
    echo '⏳ Waiting for LiveKit server to be ready...'; \
    for i in {1..30}; do \
        if netcat -z localhost 7880 2>/dev/null; then \
            echo '✅ LiveKit server is ready'; \
            break; \
        fi; \
        if [ $i -eq 30 ]; then \
            echo '❌ LiveKit server failed to start'; \
            exit 1; \
        fi; \
        sleep 1; \
    done; \
    echo '🚀 Starting Token Server...'; \
    uv run python token_server.py > /var/log/token-server.log 2>&1 & \
    TOKEN_PID=$!; \
    sleep 2; \
    echo '🚀 Starting AI Agent...'; \
    uv run python agent.py start > /var/log/agent.log 2>&1 & \
    AGENT_PID=$!; \
    sleep 2; \
    echo '🚀 Starting React Frontend...'; \
    cd react-app/dist && http-server -p 4173 -a 0.0.0.0 --silent & \
    REACT_PID=$!; \
    echo ''; \
    echo '✅ All services started successfully!'; \
    echo ''; \
    echo '📍 Service URLs:'; \
    echo '   - LiveKit Server: ws://localhost:7880'; \
    echo '   - Token Server: http://localhost:8080'; \
    echo '   - React Frontend: http://localhost:4173'; \
    echo ''; \
    echo '📋 Logs available at:'; \
    echo '   - LiveKit: /var/log/livekit.log'; \
    echo '   - Token Server: /var/log/token-server.log'; \
    echo '   - Agent: /var/log/agent.log'; \
    echo ''; \
    trap 'echo \"Shutting down services...\"; kill $LIVEKIT_PID $TOKEN_PID $AGENT_PID $REACT_PID 2>/dev/null; exit 0' SIGTERM SIGINT; \
    wait $REACT_PID; \
"]
