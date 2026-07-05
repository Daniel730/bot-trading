import asyncio
import os
import sys

import pytest

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from src.services.sec_service import sec_service


@pytest.mark.asyncio
async def test_parser_robustness():
    sample_html = """
    <html>
    <body>
        <div>... preamble ...</div>
        <h1>ITEM 1A. RISK FACTORS</h1>
        <p>This is the content of risk factors. It should be captured.</p>
        <p>More risks here.</p>

        <h2>ITEM 1B. UNRESOLVED STAFF COMMENTS</h2>
        <p>This should NOT be in Item 1A.</p>

        <div>ITEM 7: MANAGEMENT'S DISCUSSION AND ANALYSIS OF FINANCIAL CONDITION</div>
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

    assert set(sections) == {"Item 1A", "Item 3", "Item 7"}

    assert "This is the content of risk factors" in sections["Item 1A"]
    assert "More risks here" in sections["Item 1A"]
    assert "ITEM 1B" not in sections["Item 1A"]
    assert "This should NOT be in Item 1A" not in sections["Item 1A"]

    assert "MANAGEMENT'S DISCUSSION AND ANALYSIS" in sections["Item 7"]
    assert "Financial results are good" in sections["Item 7"]
    assert "Item 8" not in sections["Item 7"]
    assert "This marks the end of Item 7" not in sections["Item 7"]

    assert "Legal Proceedings" in sections["Item 3"]
    assert "No major lawsuits" in sections["Item 3"]
    assert "Mine Safety Disclosures" not in sections["Item 3"]


if __name__ == "__main__":
    asyncio.run(test_parser_robustness())
