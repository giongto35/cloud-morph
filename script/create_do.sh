region=SGP1
if [ "$1" != "" ]; then
    region=$1
fi

doctl compute droplet create cloud-morph --size c-2 --image ubuntu-20-04-x64 --region $1 --tag-name cloud-morph --ssh-keys $SSHKEY --enable-backups --wait --format "PublicIPv4" --no-header
# SGP1 is the Singapore region, change to LON1 for Europe, or SFO2 for US

