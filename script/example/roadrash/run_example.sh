# Example
# mount CDROM to the path
# setup_remote with syncvolume

./interactive-wine.sh 'wine "/apps/Road_Rash_Win_Setup_EN/Game Files/RoadRash.exe"' $(pwd)/apps
./setup_remote.sh x.x.x.x /apps/Road_Rash_Win_Setup_EN syncvolume

