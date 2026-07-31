.PHONY: run refresh viewer install

# Run the full pipeline (uses caches where available)
run:
	python3 src/pipeline.py

# Run the full pipeline, ignoring all caches
refresh:
	python3 src/pipeline.py --refresh

# Serve the viewer at http://localhost:8000/viewer/
viewer:
	@test -f gaps.json || (echo "ERROR: gaps.json not found. Run 'make run' first." && exit 1)
	@cp gaps.json viewer/gaps.json
	@echo ""
	@echo "  Open in browser:"
	@echo "    Results  →  http://localhost:8000/viewer/"
	@echo "    Guide    →  http://localhost:8000/viewer/guide.html"
	@echo ""
	@echo "  Press Ctrl+C to stop"
	@echo ""
	python3 -m http.server 8000

# Install all Python dependencies
install:
	pip3 install -r requirements.txt
