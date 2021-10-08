# build
FROM debian:bullseye-slim AS build

RUN apt-get -qq update && apt-get -qq install --no-install-recommends -y \
    ca-certificates \
    wget

# go setup
ARG GO=go1.17.linux-amd64.tar.gz
RUN wget -q https://golang.org/dl/$GO \
    && rm -rf /usr/local/go \
    && tar -C /usr/local -xzf $GO
ENV PATH="${PATH}:/usr/local/go/bin"

# go deps layer
COPY go.mod go.sum ./
RUN go mod download

# app build layer
COPY pkg/shim ./pkg/shim
COPY cmd/shim ./cmd/shim
RUN GOOS=windows GOARCH=amd64 go build -o ./bin/ ./cmd/shim/shim.go

# base image
FROM debian:bullseye-slim

COPY --from=build ./bin/ /usr/local/bin/

EXPOSE 8080
