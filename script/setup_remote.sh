# Deploy to Remote server.

RPATH=/root
ssh root@$1 "cd $RPATH; git clone https://github.com/giongto35/cloud-morph.git; cd $RPATH/cloud-morph; git reset --hard; git pull;"
rsync ./config.yaml root@$1:cloud-morph/
ssh root@$1 "cd $RPATH/cloud-morph; ./setup.sh"

if [ -d "apps" ]; then
    echo "SYNCING APPS"
    rsync -r apps --exclude 'Save/*' root@$1:$RPATH/cloud-morph/winvm/
fi

if [ -d "wine" ]; then
    echo "SYNCING VOLUME"
    # For pre-setup/non-portable flow: to sync volume copy wine environment from local to server
    # copy local wine folder to remote .wine
    rsync -r wine root@$1:$RPATH
    # mount $RPATH to r
    ssh root@$1 "docker run -v $RPATH:/rpath --volume winecfg:$RPATH/.wine syncwine bash -c 'cp -rf /rpath/wine/* /root/.wine'"
fi

# Run server without supervisor
#ssh root@$1 "cd $RPATH/cloud-morph; pkill server; nohup ./server > /dev/null &> /dev/null &"
 #Run Server in supervisord
ssh root@$1 "apt-get install -y supervisor | true"
rsync ../../supervisord.conf root@$1:/etc/supervisor/conf.d
ssh root@$1 "cd $RPATH/cloud-morph; go build server.go; service supervisor stop; pkill server | true;  supervisord | true; service supervisor start;"
ssh root@$1 "iptables -t nat -A PREROUTING -i eth0 -p tcp --dport 80 -j REDIRECT --to-port 8080; iptables-save;"
