# Serve the generated MkDocs static site (./site) with nginx.
#
# ./site is a BUILD ARTIFACT, not source. It is produced by:
#
#     make portal        # python -m framegraph._docsite.build + mkdocs build
#
# Build and run the image:
#
#     make portal
#     docker build -t framegraph-docs .
#     docker run --rm -p 8080:8080 framegraph-docs
#     # open http://localhost:8080/
#
# The image runs nginx as a non-root user (uid 101) and listens on :8080.

FROM nginxinc/nginx-unprivileged:1.27-alpine

# Directory-style URLs, custom 404 page, and asset caching.
COPY docker/default.conf /etc/nginx/conf.d/default.conf

# The rendered static site.
COPY site/ /usr/share/nginx/html/

EXPOSE 8080

# Liveness: nginx must answer on the listen port.
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD wget -q -O /dev/null http://127.0.0.1:8080/ || exit 1
