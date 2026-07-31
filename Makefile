.PHONY: run refresh viewer qa install

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
	@test -f data/gaps_qa.json && cp data/gaps_qa.json viewer/gaps_qa.json || true
	@echo ""
	@echo "  Open in browser:"
	@echo "    Results       →  http://localhost:8000/viewer/"
	@echo "    Presentation  →  http://localhost:8000/viewer/guide.html"
	@test -f viewer/gaps_qa.json && echo "    QA grades     →  shown on Results page (from make qa)" || echo "    QA grades     →  run 'make qa' then 'make viewer' to show"
	@echo ""
	@echo "  Press Ctrl+C to stop"
	@echo ""
	python3 -m http.server 8000

# AI quality tester — latent need vs complaint summary (requires gaps.json + API key)
qa:
	@test -f gaps.json || (echo "ERROR: gaps.json not found. Run 'make run' first." && exit 1)
	python3 src/qa_gaps.py

# Install all Python dependencies
install:
	pip3 install -r requirements.txt
