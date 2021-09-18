taskkill /FI "ImageName eq notepad.exe" /F
taskkill /FI "ImageName eq ffmpeg.exe" /F
$app = Start-Process notepad -PassThru
sleep 2
echo $app.id
echo (Get-Process -Id $app.id)
echo (Get-Process -Id $app.id).mainWindowTitle
$title = ((Get-Process -Id $app.id).mainWindowTitle)
echo "Title"$title
sleep 2
Start-Process ffmpeg -PassThru -ArgumentList "-f gdigrab -framerate 30 -i title=`"$title`" -pix_fmt yuv420p -vf scale=1280:-2 -c:v libvpx -f rtp rtp://127.0.0.2:5004"
sleep 2

echo "Done"