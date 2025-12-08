#!/usr/bin/env bash
# Download Wine gecko and mono installers

get_hrefs() {
    local url="$1"
    local regexp="$2"
    wget -q -O- "${url}" | sed -E "s/></>\n</g" | sed -n -E "s|^.*<a href=\"(${regexp})\">.*|\1|p" | uniq
}

get_app_ver() {
    local app="${1^^}"
    local url="https://raw.githubusercontent.com/wine-mirror/wine/wine-${WINE_VER}/dlls/appwiz.cpl/addons.c"
    wget -q -O- "${url}" | grep -E "^#define ${app}_VERSION\s" | awk -F\" '{print $2}'
}

WINE_VER="$1"

if [ -z "${WINE_VER}" ]; then
    echo "Usage: $0 <wine_version>"
    exit 1
fi

for APP in "gecko" "mono"; do
    APP_VER=$(get_app_ver "${APP}")
    APP_URL="http://dl.winehq.org/wine/wine-${APP}/${APP_VER}/"
    mapfile -t FILES < <(get_hrefs "${APP_URL}" ".*\.msi")
    
    [ ! -d "/usr/share/wine/${APP}" ] && mkdir -p "/usr/share/wine/${APP}"
    for FILE in "${FILES[@]}"; do
        echo "Downloading ${FILE}"
        wget -nv -O "/usr/share/wine/${APP}/${FILE}" "${APP_URL}${FILE}"
    done
done

