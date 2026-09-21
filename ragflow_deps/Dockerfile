# This builds an image that contains the resources needed by Dockerfile
#
FROM scratch

# Copy resources downloaded via download_deps.py
COPY chrome*-153.0.8010.52-*.zip cl100k_base.tiktoken libssl*.deb tika-server-standard-3.3.0.jar tika-server-standard-3.3.0.jar.md5 uv-*-unknown-linux-gnu.tar.gz stagehand-server-v3-linux-* /

COPY nltk_data /nltk_data

COPY huggingface.co /huggingface.co
