# syntax=docker/dockerfile:1.6
# Stage 1: Build
FROM node:20-slim AS build
WORKDIR /app

# Copy lockfiles first so npm install layer is cached unless deps change.
COPY package*.json ./

# npm ci is faster and deterministic vs npm install. Cache mount keeps
# ~/.npm warm across rebuilds so unchanged deps don't re-download.
RUN --mount=type=cache,target=/root/.npm \
    npm ci --legacy-peer-deps

# Copy the rest of the frontend source and build
COPY . .
RUN npm run build

# Stage 2: Serve static files with nginx (~25MB runtime vs ~200MB node+serve)
FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
