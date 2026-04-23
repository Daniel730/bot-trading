import sys
import os
import asyncio

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from src.services.sec_service import sec_service

async def test_parser_robustness():
    print("Testing SEC Parser Robustness...")
    
    # Sample HTML with varied Item headers
    sample_html = """
    <html>
    <body>
        <div>... preamble ...</div>
        <h1>ITEM 1A. RISK FACTORS</h1>
        <p>This is the content of risk factors. It should be captured.</p>
        <p>More risks here.</p>
        
        <h2>ITEM 1B. UNRESOLVED STAFF COMMENTS</h2>
        <p>This should NOT be in Item 1A.</p>
        
        <div>ITEM 7: MANAGEMENT’S DISCUSSION AND ANALYSIS OF FINANCIAL CONDITION</div>
        <p>Financial results are good. This should be captured in Item 7.</p>
        
        <h3>Item 8. Financial Statements</h3>
        <p>This marks the end of Item 7.</p>
        
        <p>ITEM 3: Legal Proceedings</p>
        <p>No major lawsuits. This should be in Item 3.</p>
        
        <p>ITEM 4. Mine Safety Disclosures</p>
    </body>
    </html>
    """
    
    sections = sec_service.extract_sections(sample_html)
    
    # Validation
    print("\nResults:")
    for item, text in sections.items():
        print(f"\n--- {item} ---")
        if text:
            print(f"Length: {len(text)}")
            print(f"First 100 chars: {text[:100]}...")
            # Check for truncation (should not include next item)
            if item == "Item 1A" and "ITEM 1B" in text:
                print(f"❌ FAIL: {item} included next item header.")
            elif item == "Item 7" and "Item 8" in text:
                print(f"❌ FAIL: {item} included next item header.")
            else:
                print(f"✅ PASS: {item} correctly segmented.")
        else:
            print(f"❌ FAIL: {item} NOT FOUND.")

if __name__ == "__main__":
    asyncio.run(test_parser_robustness())
