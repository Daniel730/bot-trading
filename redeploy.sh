#!/bin/bash

# Configuration
BACKEND_COMPOSE="docker-compose.backend.yml"
FRONTEND_COMPOSE="docker-compose.frontend.yml"
BACKEND_DEPS="requirements.txt"
FRONTEND_DEPS="frontend/package.json"
HASH_STORE=".redeploy_hashes"

# Create hash store if it doesn't exist
mkdir -p "$HASH_STORE"

# Function to get hash of a file
get_hash() {
    md5sum "$1" | cut -d' ' -f1
}

# Function to check if packages need update
needs_package_update() {
    local dep_file="$1"
    local stored_hash_file="$HASH_STORE/$(basename "$dep_file").hash"
    
    if [ ! -f "$stored_hash_file" ]; then
        return 0 # No hash stored, assume update needed
    fi
    
    local current_hash=$(get_hash "$dep_file")
    local stored_hash=$(cat "$stored_hash_file")
    
    if [ "$current_hash" != "$stored_hash" ]; then
        return 0 # Hash changed, update needed
    fi
    
    return 1 # No update needed
}

# Function to update stored hash
update_hash() {
    local dep_file="$1"
    get_hash "$dep_file" > "$HASH_STORE/$(basename "$dep_file").hash"
}

# Redeploy Backend
redeploy_backend() {
    echo "--- Redeploying Backend ---"
    if needs_package_update "$BACKEND_DEPS"; then
        echo "Detected changes in $BACKEND_DEPS. Rebuilding backend with package updates..."
        docker-compose -f "$BACKEND_COMPOSE" build --no-cache bot mcp-server
        update_hash "$BACKEND_DEPS"
    else
        echo "No package changes detected for backend."
    fi
    docker-compose -f "$BACKEND_COMPOSE" up -d
}

# Redeploy Frontend
redeploy_frontend() {
    echo "--- Redeploying Frontend ---"
    if needs_package_update "$FRONTEND_DEPS"; then
        echo "Detected changes in $FRONTEND_DEPS. Rebuilding frontend..."
        docker-compose -f "$FRONTEND_COMPOSE" build --no-cache || {
            echo "Build failed! Tip: If you see IPv6 network errors (dial tcp [2606...]), try disabling IPv6 for Docker or ensure your DNS is working correctly."
            return 1
        }
        update_hash "$FRONTEND_DEPS"
    else
        echo "No package changes detected for frontend."
    fi
    docker-compose -f "$FRONTEND_COMPOSE" up -d
}

# Main Execution
case "$1" in
    backend)
        redeploy_backend
        ;;
    frontend)
        redeploy_frontend
        ;;
    all)
        redeploy_backend
        redeploy_frontend
        ;;
    watch)
        echo "Starting auto-redeploy watcher..."
        echo "Watching src/, scripts/, frontend/src/, execution-engine/src/, execution-engine/build.gradle.kts for changes..."

        # Initial hashes — O8 fix: include Java source so engine changes trigger a rebuild
        PREV_BACKEND_HASH=$(find src/ scripts/ execution-engine/src/ execution-engine/build.gradle.kts -type f -exec md5sum {} + 2>/dev/null | md5sum)
        PREV_JAVA_HASH=$(find execution-engine/src/ execution-engine/build.gradle.kts -type f -exec md5sum {} + 2>/dev/null | md5sum)
        PREV_FRONTEND_HASH=$(find frontend/src/ -type f -exec md5sum {} + | md5sum)
        SRC_HASH=$(find src/ scripts/ frontend/src/ execution-engine/src/ execution-engine/build.gradle.kts -type f -exec md5sum {} + 2>/dev/null | md5sum)

        while true; do
            sleep 5
            CURRENT_SRC_HASH=$(find src/ scripts/ frontend/src/ execution-engine/src/ execution-engine/build.gradle.kts -type f -exec md5sum {} + 2>/dev/null | md5sum)

            if [ "$SRC_HASH" != "$CURRENT_SRC_HASH" ]; then
                echo "Change detected! Analyzing..."

                BACKEND_HASH=$(find src/ scripts/ execution-engine/src/ execution-engine/build.gradle.kts -type f -exec md5sum {} + 2>/dev/null | md5sum)
                JAVA_HASH=$(find execution-engine/src/ execution-engine/build.gradle.kts -type f -exec md5sum {} + 2>/dev/null | md5sum)
                FRONTEND_HASH=$(find frontend/src/ -type f -exec md5sum {} + | md5sum)

                # Check if Java engine changed — rebuild execution-engine image specifically
                if [ "$PREV_JAVA_HASH" != "$JAVA_HASH" ]; then
                    echo "Java execution-engine change detected. Rebuilding..."
                    docker-compose -f "$BACKEND_COMPOSE" build --no-cache execution-engine
                    docker-compose -f "$BACKEND_COMPOSE" up -d execution-engine
                    PREV_JAVA_HASH="$JAVA_HASH"
                fi

                # Check if Python backend changed
                if [ "$PREV_BACKEND_HASH" != "$BACKEND_HASH" ]; then
                    echo "Backend change detected."
                    redeploy_backend
                    PREV_BACKEND_HASH="$BACKEND_HASH"
                fi

                # Check if frontend changed
                if [ "$PREV_FRONTEND_HASH" != "$FRONTEND_HASH" ]; then
                    echo "Frontend change detected."
                    redeploy_frontend
                    PREV_FRONTEND_HASH="$FRONTEND_HASH"
                fi

                SRC_HASH="$CURRENT_SRC_HASH"
            fi
        done
        ;;
    *)
        echo "Usage: $0 {backend|frontend|all|watch}"
        exit 1
        ;;
esac
