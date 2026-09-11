FROM mcr.microsoft.com/dotnet/sdk:10.0-noble AS build
WORKDIR /src
COPY dotnet/ dotnet/
RUN dotnet publish dotnet/FoundryLab -c Release -o /publish --no-self-contained

FROM mcr.microsoft.com/dotnet/aspnet:10.0-noble
USER root
RUN sed -i 's|http://|https://|g' /etc/apt/sources.list.d/ubuntu.sources \
    && apt-get -o Acquire::Retries=2 -o Acquire::https::Timeout=30 update \
    && apt-get -o Acquire::Retries=2 -o Acquire::https::Timeout=30 install -y --no-install-recommends python3 python3-venv ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY demo/requirements-cloud.txt /tmp/requirements.txt
RUN python3 -m venv /opt/venv && /opt/venv/bin/pip install --no-cache-dir -r /tmp/requirements.txt
COPY --from=build /publish /app/published
COPY python/ /app/python/
COPY dotnet/config.example.json /app/dotnet/config.example.json
COPY demo/ /app/demo/
RUN mkdir -p /data && chown -R app:app /data /app
ENV PATH="/opt/venv/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 LAB_DATA_ROOT=/data LAB_DOTNET_DLL=/app/published/FoundryLab.dll
USER app
EXPOSE 8080
# One process and one replica preserve the global simulation admission lock.
CMD ["gunicorn", "--chdir", "demo", "--bind", "0.0.0.0:8080", "--workers", "1", "--threads", "8", "--timeout", "210", "cloud:app"]
