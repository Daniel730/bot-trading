# Technical Research: Fix Gradle Protobuf Kotlin DSL

**Feature**: `032-fix-gradle-protobuf-dsl` | **Date**: 2026-04-07

## Problem Analysis

The `execution-engine/build.gradle.kts` file is failing to compile because it uses Groovy-style DSL syntax inside a Kotlin DSL script for the `protobuf` plugin configuration. Specifically, the error `Unresolved reference: id` occurs because `id("grpc")` is not a valid way to register or configure a plugin within the `protobuf` block in Kotlin DSL.

### Current Broken Code

```kotlin
protobuf {
    protoc {
        artifact = "com.google.protobuf:protoc:3.25.1"
    }
    plugins {
        id("grpc") {
            artifact = "io.grpc:protoc-gen-grpc-java:1.62.2"
        }
    }
    generateProtoTasks {
        all().forEach { task ->
            task.plugins {
                id("grpc") { }
            }
        }
    }
}
```

## Proposed Solution: Kotlin DSL Syntax

In Gradle Kotlin DSL, the `plugins` block inside `protobuf` is a `NamedDomainObjectContainer`. To register a new element, the `create` or `register` method should be used instead of `id`.

### Corrected Syntax

```kotlin
protobuf {
    protoc {
        artifact = "com.google.protobuf:protoc:3.25.1"
    }
    plugins {
        create("grpc") {
            artifact = "io.grpc:protoc-gen-grpc-java:1.62.2"
        }
    }
    generateProtoTasks {
        all().forEach { task ->
            task.plugins {
                create("grpc") { }
            }
        }
    }
}
```

### Verification Plan

1.  Apply the changes to `execution-engine/build.gradle.kts`.
2.  Run `./gradlew shadowJar` (or `gradle shadowJar` in the Docker environment) to verify that the DSL script compiles and the build completes successfully.
3.  Check the `build/generated/source/proto/main/grpc` directory to ensure gRPC stubs are generated.
