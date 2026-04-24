# syntax=docker/dockerfile:1.6
# Stage 1: Build
FROM gradle:8.7-jdk21 AS builder
WORKDIR /app

COPY . .

# Single layer, BuildKit Gradle cache mount keeps ~/.gradle (downloaded deps,
# wrapper, compilation cache, protoc binary) warm across rebuilds.
# `shadowJar` transitively runs generateProto + compileJava, so we don't need
# to invoke gradle three times. The chmod fixes exec bits on protoc binaries
# that can occasionally come out non-executable on some filesystems.
RUN --mount=type=cache,target=/home/gradle/.gradle,sharing=locked \
    set -eux; \
    gradle generateProto --no-daemon; \
    find /home/gradle/.gradle -name "*.exe" -exec chmod +x {} + 2>/dev/null || true; \
    gradle shadowJar --no-daemon

# Stage 2: Runtime
# Using eclipse-temurin Alpine (not distroless) so the Docker healthcheck can
# use nc -z to probe the gRPC port. Distroless has no shell tools at all.
FROM eclipse-temurin:21-jre-alpine
WORKDIR /app
COPY --from=builder /app/build/libs/execution-engine-1.0-SNAPSHOT-all.jar app.jar
EXPOSE 50051
ENTRYPOINT ["java", "-jar", "app.jar"]
