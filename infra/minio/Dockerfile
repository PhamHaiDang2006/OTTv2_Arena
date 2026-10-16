FROM golang:1.23.6-alpine3.21 AS build

ARG MINIO_COMMIT=703f51164d3d0c44af41b0d86075a1f61e4779e7
RUN apk add --no-cache git
WORKDIR /src
RUN git init . \
    && git remote add origin https://github.com/minio/minio.git \
    && git fetch --depth=1 origin "${MINIO_COMMIT}" \
    && git checkout --detach FETCH_HEAD
RUN CGO_ENABLED=0 go build -trimpath -o /out/minio .

FROM alpine:3.21.3
RUN apk add --no-cache ca-certificates curl \
    && addgroup -S -g 10001 minio \
    && adduser -S -D -H -u 10001 -G minio minio \
    && mkdir -p /data \
    && chown minio:minio /data
COPY --from=build /out/minio /usr/local/bin/minio
USER 10001:10001
EXPOSE 9000 9001
ENTRYPOINT ["/usr/local/bin/minio"]
CMD ["server", "/data", "--console-address", ":9001"]
