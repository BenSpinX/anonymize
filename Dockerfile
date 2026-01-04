# SpinX/dicomsort

FROM 47.120.11.42/basic_3p/python:3.6

MAINTAINER Ben

# Use mirror
RUN cp /etc/apt/sources.list /etc/apt/sources.list.backup \
&& echo "deb http://mirrors.aliyun.com/debian/ bullseye main contrib non-free" > /etc/apt/sources.list \
&& echo "deb-src http://mirrors.aliyun.com/debian/ bullseye main contrib non-free" >> /etc/apt/sources.list

# Install dependencies
RUN apt-get update && apt-get -y install jq

# Make directory for spinx spec (v0)
ENV SPINX /spinx/v0
WORKDIR ${SPINX}
COPY run \
     requirements.txt \
     ${SPINX}/

# Install scitran.data dependencies
RUN pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/

# Add code to determine classification from dicom descrip (label)
COPY anonymize.py ${SPINX}/anonymize.py
RUN chmod +x ${SPINX}/run*

# Set the entrypoint
ENTRYPOINT ["/spinx/v0/run"]