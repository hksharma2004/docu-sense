# docusense mcp server over stdio
# docker run -i --rm -v docusense-data:/data -v "$HOME/Documents:/docs:ro" docusense

FROM python:3.12-slim AS build

COPY --from=ghcr.io/astral-sh/uv:0.11.8 /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_NO_CACHE=1

WORKDIR /app

# deps first so code changes don't bust the layer
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

COPY README.md LICENSE ./
COPY src ./src
RUN uv sync --locked --no-dev --no-editable


FROM python:3.12-slim

RUN useradd --create-home --uid 1000 docusense \
    && mkdir -p /data /docs /opt/fastembed \
    && chown docusense /data /docs /opt/fastembed

COPY --from=build /app/.venv /app/.venv

ENV PATH="/app/.venv/bin:$PATH" \
    DOCUSENSE_HOME=/data \
    DOCUSENSE_ADD_ROOTS=/docs \
    FASTEMBED_CACHE_PATH=/opt/fastembed

USER docusense

# bake the embedding model in so the first run needs no download
RUN python -c "from fastembed import TextEmbedding; from docusense.config import get_settings; TextEmbedding(get_settings().embed_model)"

VOLUME ["/data"]

ENTRYPOINT ["docusense", "serve-mcp"]
