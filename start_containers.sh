#!/bin/bash

# 1) Lee /etc/machine-id
MID=$(cat /etc/machine-id)

# 2) Genera un fichero .env con la variable MACHINE_ID
echo "MACHINE_ID=$MID" > .env

# (Opcional) Muestra qué se generó
echo "Generado fichero .env con MACHINE_ID=$MID"

# 3) Ejecuta docker-compose usando ese .env
docker-compose up -d
