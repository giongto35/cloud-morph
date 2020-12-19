docker rm winebackup -f | true
docker run -v winecfg:/root/.wine -v $(pwd):/backup --name winebackup syncwine tar cvf /backup/backup.tar /root/.wine
#docker run --rm --volumes-from winebackup -v $(pwd):/backup syncwine bash -c "mkdir -p /dbdata; cd /dbdata; tar xvf /backup/backup.tar --strip 1"
#docker run -it --rm --volumes-from winebackup -v $(pwd):/backup syncwine bash -c "tar xvf /backup/backup.tar -C /root/.wine --strip 1 && bash"
docker run -v $(pwd):/backup --volume "winecfg:/root/.wine" syncwine bash -c "tar xvf /backup/backup.tar -C /root --strip 1 && bash"
#rsync backup.tar
# Test: cd ~/.wine/drive_c/Program\ Files\ \(x86\)/
