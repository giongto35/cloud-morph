module github.com/giongto35/cloud-morph

go 1.14

require (
	github.com/gofrs/uuid v3.3.0+incompatible
	github.com/gorilla/mux v1.8.0
	github.com/gorilla/websocket v1.4.2
	github.com/pion/rtp v1.6.0
	github.com/pion/webrtc/v2 v2.2.24
	go.etcd.io/etcd v0.0.0-00010101000000-000000000000
	gopkg.in/yaml.v2 v2.3.0
)

replace go.etcd.io/etcd => go.etcd.io/etcd v0.0.0-20200520232829-54ba9589114f
