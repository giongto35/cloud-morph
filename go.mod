module github.com/giongto35/cloud-morph

go 1.14

require (
	github.com/giongto35/cloud-game/v2 v2.3.0
	github.com/gofrs/uuid v3.3.0+incompatible
	github.com/gorilla/mux v1.8.0
	github.com/gorilla/websocket v1.4.2
	github.com/pion/rtp v1.6.1
	github.com/pion/webrtc/v2 v2.2.26
	go.etcd.io/etcd v0.0.0-20191023171146-3cf2f69b5738
	gopkg.in/yaml.v2 v2.3.0
)

replace go.etcd.io/etcd => go.etcd.io/etcd v0.0.0-20200520232829-54ba9589114f
