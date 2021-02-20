# Deploy to Remote server.

RPATH=/root
ssh root@$1 "cd $RPATH; rm -rf cloud-morph; git clone https://github.com/giongto35/cloud-morph.git"
rsync ./config.yaml root@$1:cloud-morph/
ssh root@$1 "cd $RPATH/cloud-morph; ./setup.sh"
rsync -r $2 root@$1:$RPATH/cloud-morph/winvm/apps

if [ "$3" == "syncvolume" ]; then
    echo "SYNCING VOLUME"
    # For pre-setup/non-portable flow: to sync volume copy wine environment from local to server
    # copy local wine folder to remote .wine
    rsync -r wine root@$1:$RPATH
    # mount $RPATH to r
    ssh root@$1 "docker run -v $RPATH:/rpath --volume winecfg:$RPATH/.wine syncwine cp -rf /rpath/wine/* $RPATH/.wine"
fi

# Run server. 
ssh root@$1 "cd $RPATH/cloud-morph; pkill server; nohup ./server > /dev/null &> /dev/null &"
 #Run Server in supervisord
ssh root@$1 "apt-get install -y supervisor | true"
rsync ../../supervisord.conf root@$1:/etc/supervisor/conf.d
ssh root@$1 "cd $RPATH/cloud-morph; go build server.go; supervisord | true; service supervisor stop; service supervisor start"
ssh root@$1 "iptables -t nat -A PREROUTING -i eth0 -p tcp --dport 80 -j REDIRECT --to-port 8080; iptables-save;"
