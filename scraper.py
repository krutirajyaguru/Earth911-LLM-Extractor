"""
- Extracts data by scraping a website using Playwright
- Transforms the scraped HTML content into structured JSON using an LLM
- Loads the transformed data (saving as JSON here, but could be extended to DB)
"""

from playwright.sync_api import sync_playwright
import time
from langchain_core.prompts import PromptTemplate
from langchain_community.llms import Ollama
from langchain.chains import LLMChain
from bs4 import BeautifulSoup
import json
import re
from pprint import pprint


def scrape_earth911():
    """
    Scrape recycling facility pages from Earth911 website.

    Navigates to Earth911, performs a search for 'Electronics' in zip '10001',
    retrieves URLs of the first 3 facilities, and collects their HTML content.

    Returns:
        list[str]: List of HTML content strings, one per facility page.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        page.goto("https://search.earth911.com/", timeout=60000)
        page.wait_for_load_state("networkidle")

        try:
            page.click('button[class*="fc-button"]', timeout=5000)
        except Exception:
            pass

        page.fill('input#what', 'Electronics')
        page.fill('input#where', '10001')
        page.click("#submit-location-search")

        try:
            page.wait_for_selector('select', timeout=10000)
            page.select_option('select', value="100")
        except Exception:
            print("Distance dropdown not found; continuing...")

        page.wait_for_selector('#all-listings-results ul.result-list li h2.title a', timeout=10000)
        links = page.query_selector_all('#all-listings-results ul.result-list li h2.title a')
        facility_urls = [f"https://search.earth911.com{link.get_attribute('href')}" for link in links[:3]]

        facility_htmls = []
        for url in facility_urls:
            print(f"\nOpening: {url}")
            page.goto(url)
            page.wait_for_load_state("networkidle")
            facility_htmls.append(page.content())
            time.sleep(1)

        browser.close()
        return facility_htmls


template = """
You are a helpful assistant. Extract structured JSON from the following recycling facility description.

Required fields (output exactly in this structure):
[
  {{
    "business_name": "...",
    "last_update_date": "...",
    "street_address": "...",
    "materials_category": ["..."],
    "materials_accepted": ["..."]
  }}
]

Rules:
- Output only valid JSON.
- "materials_category" and "materials_accepted" must be lists of strings.
- Do NOT add extra fields like "services", "notes", etc.
- No markdown, comments, or explanations.
- Return only the JSON array.

Facility content:
{entry_text}

Output:
"""

prompt = PromptTemplate.from_template(template)
llm = Ollama(model="mistral")
chain = LLMChain(llm=llm, prompt=prompt)


def clean_json_string(json_str):
    """
    Clean the raw JSON string output by removing extra text and fixing format issues.

    Parameters:
        json_str (str): Raw string output from the LLM.

    Returns:
        str: Cleaned JSON string ready for parsing.
    """
    json_str = re.split(r'\n\s*(Note:|Explanation:|Output:)', json_str)[0].strip()
    json_str = re.sub(r',(\s*[}\]])', r'\1', json_str)
    json_str = re.sub(r'{\s*"name"\s*:\s*"([^"]+)"\s*}', r'"\1"', json_str)

    if json_str.startswith('{') and not json_str.strip().startswith('['):
        json_str = f"[{json_str}]"

    return json_str.strip()


def extract_visible_text(html):
    """
    Extract visible text from HTML by removing script and style tags.

    Parameters:
        html (str): Raw HTML content.

    Returns:
        str: Visible text suitable for LLM input.
    """
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    return soup.get_text(separator=" ", strip=True)


def validate_structure(entry):
    """
    Validate that the entry dictionary contains all required keys with correct data types.

    Parameters:
        entry (dict): Parsed JSON dictionary representing a facility.

    Returns:
        tuple[bool, str]: (True, "Valid") if valid, else (False, error message).
    """
    required_keys = {
        "business_name": str,
        "last_update_date": str,
        "street_address": str,
        "materials_category": list,
        "materials_accepted": list,
    }
    for key, expected_type in required_keys.items():
        if key not in entry:
            return False, f"Missing key: {key}"
        if not isinstance(entry[key], expected_type):
            return False, f"Wrong type for {key}: expected {expected_type.__name__}"
    return True, "Valid"


def extract_materials_accepted(html):
    """
    Extract a list of accepted materials from the HTML table with class 'materials-accepted'.

    Parameters:
        html (str): Facility page HTML content.

    Returns:
        list[str]: List of material names accepted at the facility.
    """
    soup = BeautifulSoup(html, "html.parser")
    materials = []
    rows = soup.select("table.materials-accepted tr")
    for row in rows:
        material_cell = row.find("td", class_="material-name")
        if material_cell:
            material_name = material_cell.get_text(strip=True)
            if material_name:
                materials.append(material_name)
    return materials


def classify_with_ollama(entry_html):
    """
    Use LangChain and Ollama LLM to extract structured JSON from facility HTML text.

    Cleans and parses the LLM output and validates the result.

    Parameters:
        entry_html (str): HTML content of the facility page.

    Returns:
        dict: Parsed structured data or error dictionary with 'error' key on failure.
    """
    try:
        raw_response = chain.invoke({"entry_text": extract_visible_text(entry_html)})["text"]

        if "```json" in raw_response:
            raw_response = raw_response.split("```json")[-1].split("```")[0].strip()

        cleaned = clean_json_string(raw_response)
        parsed = json.loads(cleaned)

        if isinstance(parsed, list):
            parsed = parsed[0]

        # Override materials fields with extracted data from HTML
        parsed["materials_category"] = ["Electronics"]
        parsed["materials_accepted"] = extract_materials_accepted(entry_html)

        valid, message = validate_structure(parsed)
        if not valid:
            return {"error": f"Validation error: {message}", "raw_output": parsed}
        return parsed

    except Exception as e:
        return {"error": f"JSON decode error: {str(e)}", "raw_output": raw_response}


def main():
    """
    Execute ETL pipeline:
    - Scrape facility pages
    - Transform HTML content to structured JSON via LLM and parsing
    - Save results to a JSON file
    """
    raw_facilities = scrape_earth911()
    structured_entries = []

    print(f"\nProcessing {len(raw_facilities)} links data...\n")

    for idx, raw_html in enumerate(raw_facilities, 1):
        print(f"Link #{idx}...")
        structured = classify_with_ollama(raw_html)
        pprint(structured)
        structured_entries.append(structured)

    with open("structured_recycling_data.json", "w") as f:
        json.dump(structured_entries, f, indent=2)

    print("\nAll entries processed and saved to 'structured_recycling_data.json'")


if __name__ == "__main__":
    main()
