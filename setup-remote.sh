ssh root@$1 cat <<EOF >> setup.sh
#!/usr/bin/env bash
apt-get update
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh
apt-get install -y golang-go
go build server.go
mkdir -p ./winvm/games/
cd ./winvm
docker build . -t syncwine
EOF

#ssh root@$1 "bash setup.sh"
# scp ./config.yaml root@$1:cloud-morph/

# Start server by running
# - ./server
# open browser at addresss :8080

