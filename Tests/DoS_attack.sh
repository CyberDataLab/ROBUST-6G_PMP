for i in $(seq 1 50); do
  curl -s http://10.0.2.15:8005/servlet/ServletExec > /dev/null
done