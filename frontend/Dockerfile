# Stage 1: Build
FROM node:20-slim AS build
WORKDIR /app
COPY package*.json ./
RUN npm install --legacy-peer-deps
COPY . .
RUN npm run build

# Stage 2: Serve
# Reusing node:20-slim to avoid pulling new images (nginx:alpine) and bypass network issues
FROM node:20-slim
WORKDIR /app

# Install a simple static server
RUN npm install -g serve

COPY --from=build /app/dist /app/dist

EXPOSE 80

# Serve the static files on port 80
CMD ["serve", "-s", "dist", "-l", "80"]
