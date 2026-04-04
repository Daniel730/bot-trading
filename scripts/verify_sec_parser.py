import asyncio
import os
import argparse
from dotenv import load_dotenv
from edgar import set_identity, Company

load_dotenv()

async def verify_ticker(ticker: str):
    user_agent = os.getenv("SEC_USER_AGENT")
    if not user_agent:
        print("ERROR: SEC_USER_AGENT not found in environment.")
        return

    set_identity(user_agent)
    
    print(f"--- Verifying Ticker: {ticker} ---")
    try:
        company = Company(ticker)
        print(f"CIK: {company.cik}")
        
        filings = company.get_filings(form=["10-K", "10-Q"])
        latest_filing = filings.latest()
        print(f"Latest Filing: {latest_filing.form} on {latest_filing.filing_date}")
        
        # In edgartools, we can get items from the filing
        doc = latest_filing.obj()
        
        # Testing Item 1A (Risk Factors) extraction
        print("\nChecking Risk Factors (Item 1A)...")
        risk_factors = doc.get_item("Item 1A")
        if risk_factors:
            print(f"Found Risk Factors. Length: {len(risk_factors)} chars")
            print(f"Snippet: {risk_factors[:200]}...")
        else:
            print("Risk Factors (Item 1A) not found or not parsable.")

        # Testing MD&A extraction
        print("\nChecking MD&A (Item 7/Part I Item 2)...")
        mda = doc.get_item("Item 7") or doc.get_item("Part I Item 2")
        if mda:
            print(f"Found MD&A. Length: {len(mda)} chars")
            print(f"Snippet: {mda[:200]}...")
        else:
            print("MD&A not found.")

    except Exception as e:
        print(f"ERROR: Failed to verify {ticker}: {str(e)}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", type=str, required=True, help="Ticker to verify")
    args = parser.parse_args()
    
    asyncio.run(verify_ticker(args.ticker))
