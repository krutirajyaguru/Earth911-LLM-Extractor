# Earth911-LLM-Extractor

A solution for scraping recycling facility data from [Earth911](https://search.earth911.com/) and structuring it using LLMs (via LangChain and Ollama). Combines modern web scraping with AI-assisted data extraction and validation.

---

## Prompting Strategy

### 1. How did you guide the LLM to identify and classify materials?

I designed a **structured and explicit prompt** using LangChain’s `PromptTemplate`, where I guided the LLM with:

- A strict JSON format including keys like:
  - `"business_name"`
  - `"last_update_date"`
  - `"materials_category"`
  - `"materials_accepted"`
- Clear instructions that:
  - `materials_category` and `materials_accepted` **must be lists of strings**
  - **No extra keys, markdown, or comments** should be returned
- A `{entry_text}` placeholder to dynamically inject raw HTML or visible content

#### This ensures:
- The LLM focuses only on required data.
- The output is clean, machine-readable JSON.

> Note: While the LLM worked well for most fields, it struggled with `materials_accepted`.  
> I extracted this field directly from HTML using BeautifulSoup instead.

---

### 2. How did you structure your pipeline?

I used a **modular pipeline** approach:

#### Tools Used:
- **Playwright (Python):** Modern, fast scraper that handles dynamic pages better than Selenium
- **LangChain + Ollama:** For local LLM calls (e.g., Mistral)
- **BeautifulSoup:** For clean and reliable HTML parsing
- **Custom validation logic:** To enforce JSON schema after LLM output

#### Pipeline Steps:
1. Scrape top 3 facility URLs from Earth911 using Playwright
2. For each facility:
   - Extract visible HTML
   - Inject into the LLM prompt
3. Post-process the LLM output:
   - **Override `materials_accepted`** using BeautifulSoup (parsed from `.material_name`)
   - **Force `materials_category`** to `["Electronics"]`
4. Validate and save:
   - Check each entry for correct keys and value types
   - Save all results (even partial or faulty ones) for manual review if needed
5. Export final output as structured `.json`

---

## Handling Edge Cases

### Nested HTML
- Used BeautifulSoup with **deep CSS selectors** (like `td.material-name`)
- Handles tags like `<div>`, `<span>`, or nested `<table>` layouts

### Map-only or Broken Address Info
- Earth911 sometimes shows address as a **map placeholder**
- I avoid relying on JS-loaded data or map components
- Instead, I extract only **visible, static text**
- Fallback: use `soup.get_text()` to grab everything visible if selectors fail

### Inconsistent Labels or Missing Keys
- After LLM runs, I **validate the JSON** to check:
  - All required fields are present
  - All fields are the correct type (e.g. list, string)
- If something’s wrong:
  - The entry is flagged with an `"error"` field
  - The pipeline **keeps running** — nothing breaks
  - Even broken entries are **saved** for manual inspection later

---

## Strengths and Limitations of This LLM-Based Method

### Strengths

- **Flexible**: Works across different HTML layouts (thanks to prompt + code-based fallback)
- **Adaptable**: Can scrape other recycling materials (just change the "what" field)
- **Cost-effective**: Runs on local LLMs (Ollama) — no API cost
- **Hybrid power**: Combines LLM + traditional scraping — each covers the other’s weaknesses

---

### Limitations

- LLMs may sometimes **hallucinate** or **miss fields**
- LLM output can be **messy or inconsistent** — needs cleaning
- Output quality **depends heavily on prompt formatting**
- If Earth911 **changes their HTML/JS**, scraping logic might break and need updates

---

## Output Example

```json
[
  {
    "business_name": "Green Earth Recycling",
    "last_update_date": "July 12, 2023",
    "street_address": "123 Recycle Lane, New York, NY 10001",
    "materials_category": ["Electronics"],
    "materials_accepted": ["Laptops", "Cell Phones", "Batteries"]
  }
]
