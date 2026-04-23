# Stage 1: Build
FROM gradle:8.7-jdk21 AS builder
WORKDIR /app
COPY . .
RUN gradle generateProto --no-daemon; \
    find /home/gradle/.gradle -name "*.exe" -exec chmod +x {} \; && \
    gradle shadowJar --no-daemon

# Stage 2: Runtime
# Using eclipse-temurin Alpine (not distroless) so the Docker healthcheck can
# use nc -z to probe the gRPC port. Distroless has no shell tools at all.
FROM eclipse-temurin:21-jre-alpine
WORKDIR /app
COPY --from=builder /app/build/libs/execution-engine-1.0-SNAPSHOT-all.jar app.jar
EXPOSE 50051
ENTRYPOINT ["java", "-jar", "app.jar"]
