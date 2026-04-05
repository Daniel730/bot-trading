# Stage 1: Build
FROM eclipse-temurin:21-jdk-alpine AS builder
WORKDIR /app
COPY . .
RUN ./gradlew build --no-daemon

# Stage 2: Runtime
FROM gcr.io/distroless/java21-debian12
WORKDIR /app
COPY --from=builder /app/build/libs/execution-engine-1.0-SNAPSHOT-all.jar app.jar
EXPOSE 50051
ENTRYPOINT ["java", "-jar", "app.jar"]
