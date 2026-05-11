#!/bin/sh

echo "Starting Falco..."

exec /usr/bin/falco \
  -A \
  -c /etc/Falco/falco.yaml \

