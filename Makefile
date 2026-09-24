# Gewässerstammbaum — build targets. `make help` lists them.
#
# Tier 1 (Python stdlib only):  check fix site csv geometry
# Tier 2 (node + Playwright):   smoke poster screenshots
# Tier 3 (heavy geo stack):     sources base trace geo  — needs requirements-geo.txt

PY ?= python3
NODE ?= node

.PHONY: help all check fix site csv geometry smoke poster screenshots fonts sources base trace geo serve clean

help:            ## list targets
	@grep -E '^[a-z]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  make %-12s %s\n", $$1, $$2}'

all: site csv    ## validate, build the page and the CSV

check:           ## validate data/waters (and generated geometry)
	$(PY) scripts/validate.py

fix:             ## rewrite data/waters canonically (file placement, key order)
	$(PY) scripts/validate.py --fix

site: check      ## dist/index.html, dist/gewaesser.json, build/poster.html
	$(PY) scripts/build_site.py

csv:             ## dist/gewaesser-deutschland.csv
	$(PY) scripts/export_csv.py

geometry:        ## recompute drawn courses from committed inputs (stdlib only)
	$(PY) scripts/build_geometry.py

smoke: site      ## headless browser test of dist/index.html
	$(NODE) scripts/render.mjs smoke

fonts:           ## download poster fonts into build/fonts
	$(PY) scripts/fetch_sources.py --fonts

poster: site fonts  ## dist/gewaesserstammbaum-a0.pdf
	$(NODE) scripts/render.mjs poster

screenshots: site   ## docs/img/*.png for the README
	$(NODE) scripts/render.mjs screenshots

sources:         ## download raw geodata into raw/ (heavy tier)
	$(PY) scripts/fetch_sources.py

base: sources    ## data/generated/{base,states,ne_rivers}.json from raw/
	$(PY) scripts/prepare_base.py

trace: sources   ## data/generated/traced.json from the GSHHG network
	$(PY) scripts/trace_rivers.py

geo: base trace geometry  ## full geometry rebuild from raw sources

serve: site      ## http://localhost:8000
	$(PY) -m http.server -d dist 8000

clean:           ## remove build/ and dist/
	rm -rf build dist
