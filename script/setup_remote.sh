# Deploy to Remote server.

RPATH=/root
ssh root@$1 "cd $RPATH;git clone -b Fix-chore https://github.com/giongto35/cloud-morph.git"
rsync ./config.yaml root@$1:cloud-morph/
ssh root@$1 "cd $RPATH/cloud-morph; ./setup.sh"
rsync -r $2 root@$1:$RPATH/cloud-morph/winvm/apps

if [ "$3" == "syncvolume" ]; then
    # For pre-setup/non-portable flow: to sync volume copy wine environment from local to server
    docker rm winebackup -f | true
    docker run -v winecfg:$RPATH/.wine -v $(pwd):/backup --name winebackup syncwine tar cvf /backup/backup.tar $RPATH/.wine
    scp backup.tar root@$1:$RPATH
    ssh root@$1 "docker run -v $RPATH:/backup --volume winecfg:$RPATH/.wine syncwine bash -c \"tar xvf /backup/backup.tar -C $RPATH --strip 1\""
fi

# Run server. Can modify to wrap in supervisor to make server more reliable
ssh root@$1 "cd $RPATH/cloud-morph; pkill server; nohup ./server > /dev/null &> /dev/null &"
