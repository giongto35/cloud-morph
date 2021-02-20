# Deploy to Remote server.

RPATH=/root
ssh root@$1 "cd $RPATH; rm -rf cloud-morph; git clone https://github.com/giongto35/cloud-morph.git"
rsync ./config.yaml root@$1:cloud-morph/
ssh root@$1 "cd $RPATH/cloud-morph; ./setup.sh"
rsync -r $2 root@$1:$RPATH/cloud-morph/winvm/apps

if [ "$3" == "syncvolume" ]; then
    # Sync precreated wine environment (from lutris for example). Copy wine environment from local to server
    docker rm winebackup -f | true
    docker run -v winecfg:$RPATH/.wine -v $(pwd):/backup --name winebackup syncwine tar cvf /backup/backup.tar $RPATH/wine
    scp backup.tar root@$1:$RPATH
    ssh root@$1 "docker run -v $RPATH:/backup --volume winecfg:$RPATH/.wine syncwine bash -c \"tar xvf /backup/backup.tar -C $RPATH --strip 1\""
fi

# Run server. 
#ssh root@$1 "cd $RPATH/cloud-morph; pkill server; nohup ./server > /dev/null &> /dev/null &"
# Run Server in supervisord
ssh root@$1 "apt-get install -y supervisor | true"
rsync ../../supervisord.conf root@$1:/etc/supervisor/conf.d
ssh root@$1 "cd $RPATH/cloud-morph; go build server.go; supervisord | true; service supervisor stop; service supervisor start"
# set port 8080 as 80
ssh root@$1 "iptables -t nat -A PREROUTING -i eth0 -p tcp --dport 80 -j REDIRECT --to-port 8080; iptables-save;"
