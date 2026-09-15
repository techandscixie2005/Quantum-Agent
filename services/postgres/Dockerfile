# Build the same pgvector release when the Docker Hub mirror is unavailable.
ARG POSTGRES_IMAGE=public.ecr.aws/docker/library/postgres:15.19-bookworm
FROM ${POSTGRES_IMAGE} AS build

ADD --checksum=sha256:10bf9938906e5d643bbc4a7eea104b6f57ba4898e5b76b20e60484ea1d5a7f8f https://codeload.github.com/pgvector/pgvector/tar.gz/refs/tags/v0.8.6 /tmp/pgvector.tar.gz
RUN apt-get update \
    && apt-get install --yes --no-install-recommends build-essential postgresql-server-dev-15 \
    && tar -xzf /tmp/pgvector.tar.gz -C /tmp \
    && make -C /tmp/pgvector-0.8.6 OPTFLAGS="" \
    && make -C /tmp/pgvector-0.8.6 install DESTDIR=/opt/pgvector

FROM ${POSTGRES_IMAGE}
COPY --from=build /opt/pgvector/ /
COPY --from=build /tmp/pgvector-0.8.6/LICENSE /usr/share/doc/pgvector/LICENSE
