# Build Sandbox Image 
if (!(Test-Path -Path "winvm/pkg")) {
    mkdir -p winvm/pkg
}
if (!(Test-Path -Path "winvm/pkg/ffmpeg")) {
    echo "Install FFMPEG"
    Invoke-WebRequest -Uri "https://www.gyan.dev/ffmpeg/builds/ffmpeg-git-full.7z" -OutFile winvm/pkg/ffmpeg.7z
    mkdir -p winvm/pkg/ffmpeg
    7z e winvm/pkg/ffmpeg.7z  -owinvm/pkg/ffmpeg
}