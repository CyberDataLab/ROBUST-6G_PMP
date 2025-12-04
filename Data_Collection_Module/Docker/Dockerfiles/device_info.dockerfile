#sudo docker build -f ./Data_Collection_Module/Docker/Dockerfiles/device_info.dockerfile -t device_info_robust6g:latest .

FROM alpine:3.23.0

RUN apk add --update --no-cache python3
RUN apk add py3-pip
RUN pip install flask

COPY Data_Collection_Module/Docker/Entrypoints/entrypoint_device_info.py /usr/local/bin/entrypoint_device_info.py

RUN chmod +x /usr/local/bin/entrypoint_device_info.py


ENTRYPOINT ["/usr/bin/python3", "/usr/local/bin/entrypoint_device_info.py" ]