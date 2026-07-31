.PHONY: run refresh viewer install

# Run the full pipeline (uses caches where available)
run:
	python3 src/pipeline.py

# Run the full pipeline, ignoring all caches
refresh:
	python3 src/pipeline.py --refresh

# Serve the viewer at http://localhost:8000/viewer/
viewer:
	@echo "Viewer → http://localhost:8000/viewer/"
	python3 -m http.server 8000

# Install all Python dependencies
install:
	pip3 install -r requirements.txt
