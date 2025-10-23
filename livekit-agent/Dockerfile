# Monolithic Docker Image for LiveKit Voice Agent
# Includes: LiveKit Server, Python Agent, Token Server, and React Frontend
# syntax=docker/dockerfile:1
#
# Note: --platform=linux/amd64 is required because inferedge-moss-core
# only provides prebuilt wheels for x86_64 Linux, ARM Mac, and Windows
# but not for Linux ARM64 (aarch64). This ensures compatibility.

# =============================================================================
# Stage 1: Build React Frontend
# =============================================================================
# Force amd64 platform for inferedge-moss-core compatibility (see note above)
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
# Force amd64 platform for inferedge-moss-core compatibility (see note above)
FROM --platform=linux/amd64 debian:bookworm-slim

# Prevent interactive prompts during installation
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PATH="/root/.local/bin:$PATH" \
    UV_SYSTEM_PYTHON=1

# Production LiveKit Configuration (required environment variables):
# LIVEKIT_API_KEY - API key for LiveKit server authentication
# LIVEKIT_API_SECRET - API secret for LiveKit server authentication  
# LIVEKIT_TURN_URL - TURN server URL for WebRTC connectivity (e.g., turn:your-turn-server.com:3478)
# LIVEKIT_TURN_USERNAME - TURN server username (if required)
# LIVEKIT_TURN_CREDENTIAL - TURN server password (if required)

# Install system dependencies
RUN apt-get update && apt-get install -y \
    # Supervisor for process management
    supervisor \
    # Python build dependencies
    python3.11 \
    python3-pip \
    python3-dev \
    gcc \
    g++ \
    # Node.js dependencies
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
# This amd64 binary is correct because we are in an amd64 container
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
# This will now succeed because we're on an amd64 (x86_64) platform
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
        "gunicorn>=21.0.0" \
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

# --- Supervisor Configuration ---
# Copy the supervisor config file
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf
# Create the log directory for supervisor
RUN mkdir -p /var/log/supervisor

# Expose all required ports
# 7880: LiveKit HTTP API
# 7881: LiveKit WebSocket
# 7882: LiveKit UDP (TURN)
# 8080: Token Server (Flask/Gunicorn)
# 4173: React Frontend (http-server)
EXPOSE 7880 7881 7882/udp 8080 4173

# Health check - validates all critical services are responding
# Start period allows time for agent model loading (~20s) and service startup
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD netcat -z localhost 7880 && netcat -z localhost 8080 && netcat -z localhost 4173 || exit 1

# Start supervisord to manage all services (LiveKit, Agent, Token Server, React)
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]