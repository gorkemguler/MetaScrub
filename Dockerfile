# MetaScrub — bulk metadata scrubber.
#
# Ships the [api] extra so the container can run either interface out of
# the box: the local drag-and-drop web UI (default CMD) or the job-based
# REST API (override CMD).
#
# Build:  docker build -t metascrub .
# Run (web UI):
#   docker run --rm -p 127.0.0.1:8770:8770 -v "$(pwd)/metascrub_cleaned:/data" metascrub
# Run (REST API), overriding the default CMD:
#   docker run --rm -p 127.0.0.1:8000:8000 -v "$(pwd)/metascrub_cleaned:/data" metascrub \
#     api --host 0.0.0.0 --port 8000 --output-dir /data
# Run (one-off directory scrub), mounting the folder to clean:
#   docker run --rm -v "$(pwd)/docs:/work" metascrub clean /work --out /work/cleaned

FROM python:3.12-slim

LABEL org.opencontainers.image.title="MetaScrub" \
      org.opencontainers.image.description="Bulk metadata scrubbing for PDF/Office/image files (MetaScout's remediation companion)" \
      org.opencontainers.image.source="https://github.com/gorkemguler/MetaScrub" \
      org.opencontainers.image.licenses="MIT"

# libimage-exiftool-perl: required for image scrubbing (EXIF/IPTC/XMP/GPS).
# PDF, modern Office, ODF and SVG scrubbing are pure Python and need no
# system package. Scrubbing legacy .doc/.xls/.ppt needs LibreOffice — add
# `libreoffice-core libreoffice-writer libreoffice-calc libreoffice-impress`
# to the line below if you need it (adds a few hundred MB).
RUN apt-get update && apt-get install -y --no-install-recommends \
        libimage-exiftool-perl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install --no-cache-dir '.[api,image-fallback]'

# Cleaned copies + run reports (report.html / report.json / cleaned/) land
# here — mount a volume at /data to get them back onto the host.
RUN mkdir -p /data
VOLUME /data

# 8770 = web UI (default CMD). 8000 = REST API (only if you override CMD).
EXPOSE 8770 8000

ENTRYPOINT ["metascrub"]
# --host 0.0.0.0 so the port is reachable from outside the container at
# all. That is NOT the same as being reachable from outside the host —
# that depends on how you publish the port (`-p` / compose `ports:`).
# Neither the web UI nor the API has any authentication: bind to
# 127.0.0.1 on the host side unless an authenticating proxy sits in front.
CMD ["web", "--host", "0.0.0.0", "--port", "8770", "--output-dir", "/data", "--no-open-browser"]
