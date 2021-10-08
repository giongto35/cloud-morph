#!/usr/bin/env sh
pwd

export DOCKER_BUILDKIT=1
docker build -t cloud-morph-shim-sys -f ./build/system.Dockerfile ./build/ &&
docker build -t cloud-morph-shim -f ./build/shim.Dockerfile . &&
docker build -t cloud-morph-shim-all -f ./build/full.Dockerfile .
