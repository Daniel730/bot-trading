# Feature Specification: Fix Gradle Protobuf Kotlin DSL

**Feature Branch**: `032-fix-gradle-protobuf-dsl`  
**Created**: 2026-04-07  
**Status**: Draft  
**Input**: User description: "feature=\"032-fix-gradle-protobuf-kotlin-dsl\" context=\"execution-engine/build.gradle.kts\" requirements=\"1. Refactor the protobuf block to use Kotlin DSL syntax. 2. Replace 'id(\\\"grpc\\\")' with 'create(\\\"grpc\\\")' inside the protobuf.plugins block. 3. Replace 'id(\\\"grpc\\\")' with 'create(\\\"grpc\\\")' inside the generateProtoTasks plugins block. 4. Ensure the build compiles successfully without unresolved reference errors.\""

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Compile Execution Engine (Priority: P1)

As a developer, I want the Java execution engine to compile without script errors so that I can build and deploy the service.

**Why this priority**: High. The build system is currently broken, preventing any development or deployment of the execution engine.

**Independent Test**: Can be fully tested by running a build command on the execution engine and delivers a successful compilation and artifact generation.

**Acceptance Scenarios**:

1. **Given** a broken `build.gradle.kts` with unresolved `id("grpc")` references, **When** I run the build command, **Then** the build fails with "Unresolved reference: id".
2. **Given** the refactored `build.gradle.kts` with `create("grpc")` syntax, **When** I run the build command, **Then** the build completes successfully without DSL compilation errors.

### Edge Cases

- What happens when a new gRPC plugin version is introduced? The syntax should remain consistent as it's a Kotlin DSL requirement for `NamedDomainObjectContainer`.
- How does the system handle missing proto files? The build should fail with a clear "no proto files found" error rather than a DSL script error.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST support Kotlin DSL syntax in `execution-engine/build.gradle.kts` for the `com.google.protobuf` plugin configuration.
- **FR-002**: The `protobuf.plugins` block MUST use `create("grpc")` to register the gRPC plugin locator.
- **FR-003**: The `generateProtoTasks` block MUST use `create("grpc")` within the `plugins` configuration for each task.
- **FR-004**: The build script MUST resolve all references and compile successfully using the Gradle Kotlin DSL.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The `execution-engine` build completes successfully in under 3 minutes in a clean environment.
- **SC-002**: 100% of DSL compilation errors related to "Unresolved reference: id" are eliminated from the build logs.
- **SC-003**: Successful generation of Java gRPC stubs and Protobuf message classes upon build completion.

## Assumptions

- The project uses Gradle with the Kotlin DSL (`.kts`).
- The `com.google.protobuf` plugin version 0.9.4 or compatible is being used.
- The developer has a compatible JDK (v21) installed or provided via the build environment.
