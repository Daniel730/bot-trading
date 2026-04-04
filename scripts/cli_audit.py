import os
import sys

def run_audit():
    print("--- Senior Developer Project Audit ---")
    
    # 1. Check for .env file
    if os.path.exists(".env"):
        print("✓ .env file found.")
    else:
        print("✗ .env file missing. Check .env.template.")
        
    # 2. Check for critical services
    services = ["data_service.py", "risk_service.py", "kalman_service.py"]
    for s in services:
        path = os.path.join("src", "services", s)
        if os.path.exists(path):
            print(f"✓ Service {s} exists.")
        else:
            print(f"✗ Service {s} missing from src/services.")

    # 3. Check for tests
    test_count = sum(len(files) for _, _, files in os.walk("tests") if any(f.startswith("test_") for f in files))
    print(f"✓ Found {test_count} tests in /tests.")
    
    if test_count < 10:
        print("⚠ Low test coverage detected.")

    # 4. Check for active specs
    specs = [d for d in os.listdir("specs") if os.path.isdir(os.path.join("specs", d))]
    print(f"✓ Active feature specs: {len(specs)}")
    
    # 5. Type Hint Check (Sample)
    with open("src/config.py", "r") as f:
        content = f.read()
        if ":" in content and "->" in content:
            print("✓ Type hints detected in src/config.py.")
        else:
            print("⚠ Type hints missing in src/config.py.")

if __name__ == "__main__":
    run_audit()
