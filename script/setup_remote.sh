RPATH=/root
ssh root@$1 "cd $RPATH;git clone https://github.com/giongto35/cloud-morph.git"
scp ./config.yaml root@$1:cloud-morph/
ssh root@$1 "cd $RPATH/cloud-morph; ./setup.sh"
scp -r $2 root@$1:$RPATH/cloud-morph/winvm/apps
ssh root@$1 "cd $RPATH/cloud-morph; pkill server; nohup ./server > /dev/null &> /dev/null &"
