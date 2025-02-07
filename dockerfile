#sudo docker build -t fluentd_robust6g:latest .

FROM fluentd:v1.18.0-debian-1.0

USER root

# Instalar dependencias de compilación (Debian)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ruby-dev \
    libsystemd-dev \
    && rm -rf /var/lib/apt/lists/*

# Instalar Python y psutil mediante apt-get porque con pip no funciona. Vamos a usarlo para extraer metricas del host con un script 
RUN apt-get update && \
    apt-get install -y python3 python3-psutil python3-dev build-essential && \
    rm -rf /var/lib/apt/lists/*

# Instalamos plugins necesarios:
# - fluent-plugin-systemd: para leer logs de systemd
# - fluent-plugin-docker_metadata_filter: para procesar metadatos de contenedores Docker
# - fluent-plugin-prometheus 1.8.6: para exponer un endpoint con metricas en formato Prometheus. Otras versiones parece que dan errores.
# - fluent-plugin-filter_typecast: version moderna de como se castean los tipos. Se usara para pasar metricas de string a float.
RUN gem install fluent-plugin-systemd fluent-plugin-docker_metadata_filter --no-document
RUN gem install fluent-plugin-prometheus -v '2.2.0' --no-document
RUN gem install fluent-plugin-filter_typecast --no-document


# Creamos el directorio de configuración si no existe y ponemos los permisos al root.
# Añadimos el directorio para scripts
#Usuario fluent quitado -> RUN mkdir -p /fluentd/log && chown fluent:fluent /fluentd/log
RUN mkdir -p /fluentd/log
RUN mkdir -p /fluentd/log/out && chown -R root:root /fluentd/log
RUN mkdir -p /fluentd/etc
RUN mkdir -p /fluentd/scripts

# Copiamos nuestro archivo de configuración local (fluent.conf) y el de scripts (health_metrics.py) al contenedor
COPY ./configuration_files/fluent.conf /fluentd/etc/
COPY ./aux_scripts/health_metrics.py /fluentd/scripts/

# Ajustamos permisos
RUN chown root:root /fluentd/etc/fluent.conf 
RUN chmod +x /fluentd/scripts/health_metrics.py

#Eliminamos la parte del usuario fluent porque no tiene permisos dentro del contenedor para leer /var/log/syslog. Por lo tanto el usuario actual seguirá siendo root. Recordemos que el contenedor tiene el log montado con "ro" desde el host, pero root puede leerlo sin inconveniente.
#RUN chown fluent:fluent /fluentd/etc/fluent.conf
#USER fluent

# Ejecutamos Fluentd con la configuración proporcionada
CMD ["fluentd", "-c", "/fluentd/etc/fluent.conf", "-p", "/fluentd/plugins", "--no-supervisor", "-vv"]

