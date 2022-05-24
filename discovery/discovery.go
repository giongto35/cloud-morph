// Standalone service for app discovery
package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"net"
	"net/http"
	"strings"
	"time"

	"github.com/gofrs/uuid"
	"github.com/gorilla/mux"
	"go.etcd.io/etcd/client/v3"
)

const (
	dialTimeout    = 2 * time.Second
	requestTimeout = 2 * time.Second
)
const addr string = ":7700"
const etcdAddr string = ":2379"

type kvstorage struct {
	kv clientv3.KV
}

type appDiscoveryMeta struct {
	ID           string `json:"id"`
	AppName      string `json:"app_name"`
	Addr         string `json:"addr"`
	AppMode      string `json:"app_mode"`
	HasChat      bool   `json:"has_chat"`
	PageTitle    string `json:"page_title"`
	ScreenWidth  int    `json:"screen_width"`
	ScreenHeight int    `json:"screen_height"`
}

type appDiscovery struct {
	storage kvstorage
}

type server struct {
	httpServer *http.Server
	httpClient *http.Client // For http get
	discovery  *appDiscovery
}

const appHostPrefix = "apphost_"

var privateIPBlocks []*net.IPNet

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
	_, err := s.kv.Put(ctx, key, value)
	if err != nil {
		return err
	}
	return nil
}

func (s *kvstorage) removeValue(ctx context.Context, key string) error {
	_, err := s.kv.Delete(ctx, key)
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

func (d *appDiscovery) addApp(h appDiscoveryMeta) (string, error) {
	ctx, _ := context.WithTimeout(context.Background(), requestTimeout)
	appID := uuid.Must(uuid.NewV4()).String()
	h.ID = appID
	b, err := json.Marshal(h)
	if err != nil {
		return "", err
	}

	return appID, d.storage.setValue(ctx, appHostPrefix+appID, string(b))
}

func (d *appDiscovery) removeApp(appID string) error {
	ctx, _ := context.WithTimeout(context.Background(), requestTimeout)
	return d.storage.removeValue(ctx, appHostPrefix+appID)
}

func (d *appDiscovery) getApps() []appDiscoveryMeta {
	var app appDiscoveryMeta
	var apps []appDiscoveryMeta

	ctx, _ := context.WithTimeout(context.Background(), requestTimeout)
	rawApps, err := d.storage.getByPrefix(ctx, appHostPrefix)
	if err != nil {
		return nil
	}

	for _, rawApp := range rawApps {
		err := json.Unmarshal(rawApp, &app)
		if err != nil {
			continue
		}
		apps = append(apps, app)
	}

	return apps
}

func (s *server) isValidIP(addr string) bool {
	ipAddr := strings.Split(addr, ":")[0]
	if isPrivateIP(net.ParseIP(ipAddr)) {
		log.Println("Skip Private IP", addr)
		return false
	}
	if !s.isAlive(addr) {
		return false
	}
	return true
}

func (s *server) isAlive(addr string) bool {
	for i := 1; i < 5; i++ {
		response, err := http.Get(fmt.Sprintf("http://%s/%s", addr, "echo"))
		if err != nil {
			log.Println(err)
			time.Sleep(5 * time.Second)
			continue
		}
		response.Body.Close()

		if response.StatusCode == http.StatusOK {
			return true
		}
		time.Sleep(5 * time.Second)
	}

	return false
}

func isPrivateIP(ip net.IP) bool {
	if ip.IsLoopback() || ip.IsLinkLocalUnicast() || ip.IsLinkLocalMulticast() {
		return true
	}

	for _, block := range privateIPBlocks {
		if block.Contains(ip) {
			return true
		}
	}
	return false
}

func (s *server) refineAppsList() {
	for range time.Tick(5 * time.Second) {
		appsMap := map[string]appDiscoveryMeta{}

		// Deduplicate
		apps := s.discovery.getApps()
		for _, app := range apps {
			if _, ok := appsMap[app.Addr]; ok {
				log.Println("Removed duplicated ", app)
				// if existed => remove the redundant
				err := s.discovery.removeApp(app.ID)
				if err != nil {
					log.Println(err)
					continue
				}
				continue
			}
			appsMap[app.Addr] = app
		}

		// Remove dead services
		for _, app := range apps {
			if !s.isValidIP(app.Addr) {
				log.Println("Removed Dead service ", app)
				err := s.discovery.removeApp(app.ID)
				if err != nil {
					log.Println(err)
					continue
				}
				continue
			}
		}
	}
}

func initializePrivateIPBlocks() {
	for _, cidr := range []string{
		"127.0.0.0/8",    // IPv4 loopback
		"10.0.0.0/8",     // RFC1918
		"172.16.0.0/12",  // RFC1918
		"192.168.0.0/16", // RFC1918
		"169.254.0.0/16", // RFC3927 link-local
		"::1/128",        // IPv6 loopback
		"fe80::/10",      // IPv6 link-local
		"fc00::/7",       // IPv6 unique local addr
	} {
		_, block, err := net.ParseCIDR(cidr)
		if err != nil {
			panic(fmt.Errorf("parse error on %q: %v", cidr, err))
		}
		privateIPBlocks = append(privateIPBlocks, block)
	}
}

func (s *server) register(w http.ResponseWriter, r *http.Request) {
	var h appDiscoveryMeta

	log.Println("Received Register Request", h)
	// Try to decode the request body into the struct. If there is an error,
	// respond to the client with the error message and a 400 status code.
	err := json.NewDecoder(r.Body).Decode(&h)
	if err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}
	if !s.isValidIP(h.Addr) {
		return
	}
	appID, err := s.discovery.addApp(h)
	if err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}
	encodedResp, err := json.Marshal(appID)
	if err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}
	go s.refineAppsList()
	w.Write(encodedResp)
}

func (s *server) remove(w http.ResponseWriter, r *http.Request) {
	var appID string
	// Try to decode the request body into the struct. If there is an error,
	// respond to the client with the error message and a 400 status code.
	err := json.NewDecoder(r.Body).Decode(&appID)
	log.Println("Received Remove Request", appID, err)
	if err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}
	err = s.discovery.removeApp(appID)
	if err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}
}

func (s *server) getApps(w http.ResponseWriter, r *http.Request) {
	type GetAppsResponse struct {
		Apps []appDiscoveryMeta `json:"apps"`
	}
	resp := GetAppsResponse{
		Apps: s.discovery.getApps(),
	}

	log.Println("Received GetApps Request")
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
	r.HandleFunc("/register", server.register)
	r.HandleFunc("/remove", server.remove)
	r.HandleFunc("/get-apps", server.getApps)

	svmux := &http.ServeMux{}
	svmux.Handle("/", r)

	httpServer := &http.Server{
		Addr:         addr,
		ReadTimeout:  10 * time.Second,
		WriteTimeout: 10 * time.Second,
		IdleTimeout:  120 * time.Second,
		Handler:      svmux,
	}

	initializePrivateIPBlocks()

	discovery := NewDiscovery(NewStorage(etcdAddr))
	server.discovery = discovery
	server.httpServer = httpServer
	server.httpClient = &http.Client{
		Timeout: 3 * time.Second,
	}
	go server.refineAppsList()

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
