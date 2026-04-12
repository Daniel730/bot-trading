plugins {
    java
    application
    id("com.google.protobuf") version "0.9.4"
    id("com.github.johnrengelman.shadow") version "8.1.1"
}

group = "com.arbitrage"
version = "1.0-SNAPSHOT"

repositories {
    mavenCentral()
}

dependencies {
    // gRPC
    implementation("io.grpc:grpc-netty-shaded:1.62.2")
    implementation("io.grpc:grpc-protobuf:1.62.2")
    implementation("io.grpc:grpc-stub:1.62.2")
    compileOnly("org.apache.tomcat:annotations-api:6.0.53")

    // R2DBC (Async PostgreSQL)
    implementation("org.postgresql:r2dbc-postgresql:1.0.5.RELEASE")
    implementation("io.r2dbc:r2dbc-pool:1.0.1.RELEASE")

    // Redis (Lettuce)
    implementation("io.lettuce:lettuce-core:6.3.2.RELEASE")

    // Utilities
    implementation("com.fasterxml.jackson.core:jackson-databind:2.17.0")
    implementation("io.micrometer:micrometer-core:1.12.4")
    implementation("org.slf4j:slf4j-api:2.0.12")
    implementation("ch.qos.logback:logback-classic:1.5.3")

    // Test
    testImplementation("org.junit.jupiter:junit-jupiter:5.10.2")
    testImplementation("org.testcontainers:postgresql:1.19.7")
    testImplementation("org.testcontainers:junit-jupiter:1.19.7")
    testImplementation("org.mockito:mockito-core:5.11.0")
}

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

application {
    mainClass.set("com.arbitrage.engine.Application")
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(21))
    }
}

tasks.test {
    useJUnitPlatform()
}

tasks.withType<com.github.jengelman.gradle.plugins.shadow.tasks.ShadowJar> {
    archiveBaseName.set("execution-engine")
    archiveClassifier.set("all")
    archiveVersion.set("1.0-SNAPSHOT")
}
