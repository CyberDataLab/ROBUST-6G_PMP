#sudo docker build -t fluentd_robust6g:latest .

FROM fluentd:v1.18.0-debian-1.0

USER root

# Dependencies (Debian)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ruby-dev \
    libsystemd-dev \
    && rm -rf /var/lib/apt/lists/*


RUN apt-get update && \
    apt-get install -y python3 python3-psutil python3-dev build-essential && \
    rm -rf /var/lib/apt/lists/*

# Telegraf plugins
# - fluent-plugin-systemd: to read systemd logs
# - fluent-plugin-docker_metadata_filter: to process metadata from Docker containers
# - fluent-plugin-prometheus 1.8.6: to expose an endpoint with metrics in Prometheus format. Other versions seem to give errors.
# - fluent-plugin-filter_typecast: modern version of how types are casted. It will be used to pass metrics from string to float.
RUN gem install fluent-plugin-systemd fluent-plugin-docker_metadata_filter --no-document
RUN gem install fluent-plugin-prometheus -v '2.2.0' --no-document
RUN gem install fluent-plugin-filter_typecast --no-document



RUN mkdir -p /fluentd/log
RUN mkdir -p /fluentd/log/out && chown -R root:root /fluentd/log
RUN mkdir -p /fluentd/etc
RUN mkdir -p /fluentd/scripts

COPY ./configuration_files/fluent.conf /fluentd/etc/
COPY ./aux_scripts/health_metrics.py /fluentd/scripts/

# Permissions
RUN chown root:root /fluentd/etc/fluent.conf 
RUN chmod +x /fluentd/scripts/health_metrics.py

CMD ["fluentd", "-c", "/fluentd/etc/fluent.conf", "-p", "/fluentd/plugins", "--no-supervisor", "-vv"]

