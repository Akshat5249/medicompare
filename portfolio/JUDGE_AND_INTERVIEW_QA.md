# Judge and interview Q&A

**How accurate is the OCR?**
On synthetic handwriting, character error is 29.4% for tesseract and 20.7% for rapidocr. I have no real handwriting results, and I expect them to be worse. That's why OCR only proposes.

**Why did you choose the engine with worse text accuracy?**
I fixed the rule before scoring: lowest validation false-match rate. tesseract won narrowly and is faster. Honestly, the false-match difference is within noise, and rapidocr reads better, so better data should revisit this.

**What is your false-match rate?**
1.5% on the test split: 1 of 67 suggestions, with a 95% upper bound of 8.0%. With so few suggestions I can't rule out rare errors, and synthetic data flatters it.

**Why is coverage so low?**
At safe thresholds, only 17.4% of readable lines get a suggestion. I chose fewer false matches over convenience. A person checks every item anyway.

**Can a user bypass verification?**
Not through the app or API for a prescription item. The server checks the status, a database constraint backs it up, and tests call the API directly. Anyone can still open a public catalogue record they choose, because that says nothing about their prescription.

**Can a user confirm the wrong medicine?**
Yes, and that's the main remaining risk. I added friction, but I haven't measured whether it works with real users.

**Is this real data?**
Ceiling prices are real, from NPPA, covering five therapeutic categories and dated March 2026. All brands, shop prices, Jan Aushadhi entries and regulatory notices are fictional and labelled.

**So does it save anyone money?**
There's no evidence yet. It has no users, and no real retail price data.

**Why not use the Jan Aushadhi data, or scrape pharmacy sites?**
The Jan Aushadhi portal's terms ask for permission first, so I need to request it. Scraping against terms isn't acceptable, and retail prices without provenance would break the product's promise.

**Why not use an LLM for everything?**
A model that picks a medicine is hard to explain, test or trust here. Matching and gating are deterministic. An optional adapter exists but is off, isn't connected to the pipeline, and has only been tested with a fake client.

**How do you handle prompt injection?**
The pipeline has no instruction channel, so injected text can only ever appear as text. The detector recognised only about half of injected lines after OCR garbled them, so I don't rely on it.

**Is this a medical device?**
I don't know, and it needs legal review. CDSCO has guidance on medical device software, which I haven't assessed against the final text. See `docs/COMPLIANCE_NOTES.md`.

**How is privacy handled?**
Metadata stripped, private storage, 7-day deletion by default, export and account deletion. Known gaps: one database role, encryption at rest left to the host, and no penetration test.

**What would you do differently?**
Seek data access before building comparison features, and involve a pharmacist much earlier.

**Did you use AI to build this?**
Yes, substantially: Claude Code wrote much of the code and documents under my direction. *(Adjust this to be accurate for you.)*

**What are you proudest of?**
Features I left out because the data couldn't support them, and tests that caught real mistakes.
