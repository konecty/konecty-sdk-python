# Imagem do konecty-cli, publicada pelo workflow Publish como konectypro/konecty-cli:<versão>.
# É a imagem do Job aplicar-metas e do CronJob deriva-metas (feature metadados-base-e-delta do
# konecty/Konecty). Instala a wheel que o próprio workflow acabou de publicar no PyPI, então a
# versão da imagem é a do pacote, byte a byte.
#
# Build local: uv build --out-dir dist-build && docker build -t konecty-cli:local .
FROM python:3.11-slim

COPY dist-build/*.whl /tmp/dist/
RUN pip install --no-cache-dir /tmp/dist/*.whl \
    && rm -rf /tmp/dist \
    && useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin konecty

# Sem root: o Job só lê o artefato e fala HTTP com o Konecty.
USER 10001
ENV PYTHONUNBUFFERED=1
ENTRYPOINT ["konecty-cli"]
CMD ["--help"]
