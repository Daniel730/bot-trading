# Stage 1: Build
FROM node:20-slim AS build
WORKDIR /app

# O8: Optimization - Copy package files first to cache npm install
COPY package*.json ./
RUN npm install --legacy-peer-deps

# Copy the rest of the frontend code
COPY . .
RUN npm run build

# Stage 2: Serve
# Reusing node:20-slim to avoid pulling new images (nginx:alpine) and bypass network issues
FROM node:20-slim
WORKDIR /app

# Install a simple static server
RUN npm install -g serve

# Only copy the build output
COPY --from=build /app/dist /app/dist

EXPOSE 80

# Serve the static files on port 80
CMD ["serve", "-s", "dist", "-l", "80"]
