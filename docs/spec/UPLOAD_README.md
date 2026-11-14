# Upload this package to Claude

Upload all four specification files in this folder with your master build prompt:
- PROJECT_BRIEF.md
- LOCATIONS.json
- DATA_SOURCES.md
- ACCEPTANCE_CRITERIA.md

Optional: add a DESIGN_REFERENCES.zip containing your own mockups/logos, and a SAMPLE_CLIMATE_DATA.csv exported from a real source (never invented measurements). Neither is required for Claude to begin.

If you already have code, provide the existing repository too, without node_modules, build artifacts, .env, API keys or secrets.

Tell Claude: "Read the attached specifications as authoritative project requirements. Build Time Travel first while keeping Earth Duet modular for features we will add later. Do not invent scientific data. Create code, test it where tools allow, and report implementation status honestly."
