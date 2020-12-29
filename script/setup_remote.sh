# Deploy to Remote server.

RPATH=zsq
ssh zsq@$1 "cd $RPATH;git clone --branch example-script https://github.com/ShanHuaSHa/cloud-morph.git test"
rsync ./config.yaml zsq@$1:cloud-morph/
ssh zsq@$1 "cd $RPATH/cloud-morph; ./setup.sh"
rsync -r $2 zsq@$1:$RPATH/cloud-morph/winvm/apps
sudo su
if [ "$3" == "syncvolume" ]; then
    # For pre-setup/non-portable flow: to sync volume copy wine environment from local to server
    docker rm winebackup -f | true
    docker run -v winecfg:$RPATH/.wine -v $(pwd):/backup --name winebackup syncwine tar cvf /backup/backup.tar $RPATH/.wine
    scp backup.tar zsq@$1:$RPATH
    ssh zsq@$1 "docker run -v $RPATH:/backup --volume winecfg:$RPATH/.wine syncwine bash -c \"tar xvf /backup/backup.tar -C $RPATH --strip 1\""
fi

# Run server. Can modify to wrap in supervisor to make server more reliable
ssh zsq@$1 "cd $RPATH/cloud-morph; pkill server; nohup ./server > /dev/null &> /dev/null &"
