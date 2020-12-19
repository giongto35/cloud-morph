RPATH=/root
ssh root@$1 "cd $RPATH;git clone https://github.com/giongto35/cloud-morph.git"
scp ./config.yaml root@$1:cloud-morph/
ssh root@$1 "cd $RPATH/cloud-morph; ./setup.sh"
scp -r $2 root@$1:$RPATH/cloud-morph/winvm/apps
#ssh root@$1 "docker run -v winecfg:/root/.wine -v $(pwd):/backup --name winebackup syncwine tar cvf /backup/backup.tar /root/.wine"

# set flag

# copy wine environment from local to server
docker rm winebackup -f | true
docker run -v winecfg:/root/.wine -v $(pwd):/backup --name winebackup syncwine tar cvf /backup/backup.tar /root/.wine
scp backup.tar root@$1:/root
ssh root@$1 "docker run -v $(pwd):/backup --volume winecfg:/root/.wine syncwine bash -c \"tar xvf /backup/backup.tar -C /root --strip 1\""

# run server
ssh root@$1 "cd $RPATH/cloud-morph; pkill server; nohup ./server > /dev/null &> /dev/null &"
