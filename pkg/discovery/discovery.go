// Standalone service for app discovery

package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"time"

	"github.com/gofrs/uuid"
	"github.com/gorilla/mux"

	"go.etcd.io/etcd/clientv3"
)

const (
	dialTimeout    = 2 * time.Second
	requestTimeout = 10 * time.Second
)
const addr string = ":7700"
const etcdAddr string = ":2379"

type kvstorage struct {
	kv clientv3.KV
}

type appHost struct {
	IP      string `json:"ip"`
	AppName string `json:"app_name"`
}

type appDiscovery struct {
	storage kvstorage
}

type server struct {
	httpServer *http.Server
	discovery  *appDiscovery
}

const appHostPrefix = "apphost_"

func (s *kvstorage) getValue(ctx context.Context, key string) ([]byte, error) {
	resp, err := s.kv.Get(ctx, key)
	if err != nil {
		return []byte{}, err
	}
	return resp.Kvs[0].Value, nil
}

func (s *kvstorage) getByPrefix(ctx context.Context, prefix string) ([][]byte, error) {
	var respVals [][]byte

	resp, err := s.kv.Get(ctx, prefix, clientv3.WithPrefix(), clientv3.WithSort(clientv3.SortByKey, clientv3.SortDescend))
	if err != nil {
		return nil, err
	}
	for _, ev := range resp.Kvs {
		respVals = append(respVals, ev.Value)
	}

	return respVals, nil
}

func (s *kvstorage) setValue(ctx context.Context, key string, value string) error {
	_, err := s.kv.Put(context.TODO(), key, value)
	if err != nil {
		return err
	}
	return nil
}

func NewStorage(addr string) kvstorage {
	cli, err := clientv3.New(clientv3.Config{
		Endpoints:   []string{etcdAddr},
		DialTimeout: dialTimeout,
	})
	if err != nil {
		log.Fatal(err)
	}
	//defer cli.Close() // make sure to close the client
	kv := clientv3.NewKV(cli)
	return kvstorage{
		kv: kv,
	}
}

func NewDiscovery(storage kvstorage) *appDiscovery {
	return &appDiscovery{
		storage: storage,
	}
}

func (d *appDiscovery) addApp(h appHost) error {
	ctx, _ := context.WithTimeout(context.Background(), requestTimeout)
	b, err := json.Marshal(h)
	if err != nil {
		return err
	}

	appID := uuid.Must(uuid.NewV4()).String()
	d.storage.setValue(ctx, appHostPrefix+appID, string(b))
	return nil
}

func (d *appDiscovery) getApps() []appHost {
	var app appHost
	var apps []appHost

	ctx, _ := context.WithTimeout(context.Background(), requestTimeout)
	rawHosts, err := d.storage.getByPrefix(ctx, appHostPrefix)
	if err != nil {
		return nil
	}

	for _, rawHost := range rawHosts {
		fmt.Println(string(rawHost))
		err := json.Unmarshal(rawHost, &app)
		if err != nil {
			continue
		}
		apps = append(apps, app)
	}

	return apps
}

func (s *server) connect(w http.ResponseWriter, r *http.Request) {
	var h appHost

	// Try to decode the request body into the struct. If there is an error,
	// respond to the client with the error message and a 400 status code.
	err := json.NewDecoder(r.Body).Decode(&h)
	if err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}
	err = s.discovery.addApp(h)
	if err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}
}

func (s *server) getApps(w http.ResponseWriter, r *http.Request) {
	fmt.Println("Received Get Request")
	type appsResp struct {
		Apps []appHost `json:"apps"`
	}
	resp := appsResp{
		Apps: s.discovery.getApps(),
	}

	encodedResp, err := json.Marshal(resp)
	if err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}
	w.Write(encodedResp)
}

func NewServer() server {
	server := server{}

	r := mux.NewRouter()
	r.HandleFunc("/connect", server.connect)
	r.HandleFunc("/get-apps", server.getApps)

	svmux := &http.ServeMux{}
	svmux.Handle("/", r)

	httpServer := &http.Server{
		Addr:         addr,
		ReadTimeout:  5 * time.Second,
		WriteTimeout: 5 * time.Second,
		IdleTimeout:  120 * time.Second,
		Handler:      svmux,
	}

	discovery := NewDiscovery(NewStorage(etcdAddr))
	server.httpServer = httpServer
	server.discovery = discovery

	return server
}

func (s *server) Run() {
	fmt.Println("Listening at", addr)
	s.httpServer.ListenAndServe()
}

func main() {
	s := NewServer()
	s.Run()
}
