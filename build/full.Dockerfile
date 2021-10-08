FROM cloud-morph-shim-sys

COPY --from=cloud-morph-shim /usr/local/bin/shim.exe /usr/local/bin/shim.exe
