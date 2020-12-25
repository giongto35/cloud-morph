doctl compute droplet create cloud-morph --size s-1vcpu-2gb --image ubuntu-20-04-x64 --region SGP1 --tag-name cloud-morph --ssh-keys $SSHKEY --enable-backups --wait --format "PublicIPv4" --no-header
#doctl compute droplet create cloud-morph --size s-4vcpu-8gb --image ubuntu-20-04-x64 --region SGP1 --ssh-keys $SSHKEY --enable-backups
