import asyncio
import sys
import os

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))

from src.services.agent_log_service import agent_logger, agent_trace
from src.services.data_service import data_service

@agent_trace("Test.level_2")
async def level_2():
    print("Triggering simulated KeyError...")
    # This will trigger a KeyError which should be caught and logged
    data = {"known_key": "val"}
    return data["missing_key"]

@agent_trace("Test.level_1")
async def level_1():
    await level_2()

async def run_test():
    print("Starting Agent-Centric Observability Test...")
    try:
        await level_1()
    except Exception as e:
        context = {
            "ticker": "AAPL",
            "api_key": "SK-SECRET-DONT-LOG-ME",
            "nested": {
                "password": "12345-secret"
            }
        }
        agent_logger.capture_error(e, context=context)
        
    if os.path.exists("AGENT_ERROR.md"):
        print("\n✅ SUCCESS: AGENT_ERROR.md was generated.")
        with open("AGENT_ERROR.md", "r") as f:
            content = f.read()
            print("\n--- AGENT_ERROR.md Content ---")
            print(content)
            
            # Verify scrubbing
            if "SK-SECRET" in content or "12345-secret" in content:
                print("\n❌ FAILED: Sensitive data was NOT scrubbed!")
            else:
                print("\n✅ SUCCESS: Sensitive data was successfully scrubbed.")
                
            # Verify path
            if "Test.level_1 -> Test.level_2" in content:
                print("✅ SUCCESS: Execution path correctly tracked.")
            else:
                print("❌ FAILED: Execution path tracking incorrect.")
    else:
        print("\n❌ FAILED: AGENT_ERROR.md was NOT generated.")

if __name__ == "__main__":
    asyncio.run(run_test())
