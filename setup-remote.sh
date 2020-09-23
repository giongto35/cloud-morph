RPATH=/root
ssh root@$1 "cd $RPATH;git clone https://github.com/giongto35/cloud-morph.git"
scp ./config.yaml root@$1:cloud-morph/
ssh root@$1 "cd $RPATH/cloud-morph; ./setup.sh"
scp -r $2 root@$1:$RPATH/cloud-morph/winvm/games
ssh root@$1:"cd $RPATH; ./server"

