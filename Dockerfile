# SpinX/dicomsort

FROM eclipse-temurin:17-jre-focal

MAINTAINER Ben
USER root

# Install dependencies (jq) and a Java runtime so we don't need a Java base image.
# Also ensure tar and ca-certificates are available for extracting the release.
RUN apt-get update && \
    apt-get -y install jq && \
    rm -rf /var/lib/apt/lists/*

ARG DCM4CHE_VER=5.34.2
ENV DCM4CHE_HOME=/opt/dcm4che-${DCM4CHE_VER}
ENV PATH="${DCM4CHE_HOME}/bin:${PATH}"

WORKDIR /opt

# Copy the binary tarball into the image
COPY dcm4che-${DCM4CHE_VER}-bin.tar.gz /tmp/

# Install minimal tools, extract, set permissions, create symlink, clean up
RUN tar -xzf /tmp/dcm4che-${DCM4CHE_VER}-bin.tar.gz -C /opt && \
    rm /tmp/dcm4che-${DCM4CHE_VER}-bin.tar.gz && \
    ln -s ${DCM4CHE_HOME} /opt/dcm4che && \
    chmod +x ${DCM4CHE_HOME}/bin/* && \
    rm -rf /var/lib/apt/lists/*

# Create an unprivileged user for running the tools
RUN useradd -m -s /bin/bash dcm4che && \
    chown -R dcm4che:dcm4che ${DCM4CHE_HOME} /opt/dcm4che

WORKDIR /home/dcm4che

# Make directory for spinx spec (v0)
ENV SPINX /spinx/v0
WORKDIR ${SPINX}
COPY run \
     manifest.json \
     deidentify.md \
     ${SPINX}/

# Add code to determine classification from dicom descrip (label)
RUN chmod +x ${SPINX}/run*

# Set the entrypoint
ENTRYPOINT ["/spinx/v0/run"]