#!/usr/bin/env bash
set -e

API_CONTAINERS=(
  tshark_robust6g
  device_info_robust6g
  flow_module_robust6g
  telegraf_robust6g
  fluentd_robust6g
  falco_robust6g
  falco_exporter_robust6g
  alert_module_robust6g
  prometheus_robust6g
  opensearch_robust6g
  opensearch-dashboards_robust6g
  logstash_robust6g
  alarm_collector_robust6g
)

echo "Stopping API-launched containers..."

for c in "${API_CONTAINERS[@]}"; do
  if docker ps -a --format '{{.Names}}' | grep -qx "$c"; then
    echo "Removing $c"
    docker rm -f "$c"
  fi
done

echo "Done."