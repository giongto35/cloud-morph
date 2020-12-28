doctl compute droplet create cloud-morph --size s-4vcpu-8gb --image ubuntu-20-04-x64 --region SFO2 --tag-name cloud-morph --ssh-keys $SSHKEY --enable-backups --wait --format "PublicIPv4" --no-header
# SGP1 is the Singapore region, change to LON1 for Europe, or SFO2 for US

