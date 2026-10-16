# ── OmniRoute AI Gateway ──
FROM node:22-alpine

WORKDIR /app

# Install dependencies needed for native modules
RUN apk add --no-cache python3 make g++ git

# Copy dependency files first for caching
COPY package.json package-lock.json* ./

# Install all dependencies
RUN npm install --legacy-peer-deps

# Copy the rest of OmniRoute
COPY . .

# Expose OmniRoute port
EXPOSE 20128

# Set environment variables for Docker
ENV PORT=20128
ENV RATE_LIMIT_MAX_WAIT_MS=300000
ENV NODE_OPTIONS="--max-old-space-size=8192"

# Run OmniRoute dev server
CMD ["npm", "run", "dev"]
