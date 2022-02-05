package main

import (
	"bytes"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"html/template"
	"log"
	"net/http"
	"net/http/pprof"
	"os"
	"os/signal"
	"time"

	"github.com/giongto35/cloud-morph/pkg/addon/textchat"
	"github.com/giongto35/cloud-morph/pkg/common/config"
	"github.com/giongto35/cloud-morph/pkg/common/cws"
	"github.com/giongto35/cloud-morph/pkg/common/ws"
	"github.com/giongto35/cloud-morph/pkg/core/go/cloudapp"
	"github.com/gorilla/mux"
	"github.com/gorilla/websocket"
)

var upgrader = websocket.Upgrader{}

const configFilePath = "config.yaml"

var curApp = "Notepad"

const embedPage string = "web/embed/embed.html"
const indexPage string = "web/index.html"
const addr string = ":8080"

var chatEventTypes = []string{"CHAT"}
var appEventTypes = []string{"OFFER", "ANSWER", "MOUSEDOWN", "MOUSEUP", "MOUSEMOVE", "KEYDOWN", "KEYUP"}
var dscvEventTypes = []string{"SELECTHOST"}

// TODO: multiplex clientID
var clientID string

// type BrowserClient struct {
// 	clientID string
// 	ws       *cws.Client
// }

type Server struct {
	appID            string
	httpServer       *http.Server
	wsClients        map[string]*cws.Client
	chat             *textchat.TextChat
	discoveryHandler *discoveryHandler
	appMeta          appDiscoveryMeta
	cappServer       *cloudapp.Server
}

type discoveryHandler struct {
	httpClient    *http.Client
	discoveryHost string
	apps          []appDiscoveryMeta
}

// TODO: sync with discovery.go
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

type initData struct {
	CurAppID string `json:"cur_app_id"`
	// App maynot be inside Apps because App can be in local, not in discovery
	App  appDiscoveryMeta   `json:"cur_app"`
	Apps []appDiscoveryMeta `json:"apps"`
}

// WSO handles all connections from user/frontend to coordinator
func (s *Server) WS(w http.ResponseWriter, r *http.Request) {
	log.Println("A user is connecting...")
	// defer func() {
	// 	if r := recover(); r != nil {
	// 		log.Println("Warn: Something wrong. Recovered in ", r)
	// 	}
	// }()

	upgrader.CheckOrigin = func(r *http.Request) bool {
		// TODO: can we be stricter?
		return true
	}
	// be aware of ReadBufferSize, WriteBufferSize (default 4096)
	// https://pkg.go.dev/github.com/gorilla/websocket?tab=doc#Upgrader
	c, err := upgrader.Upgrade(w, r, nil)
	if err != nil {
		log.Println("Coordinator: [!] WS upgrade:", err)
		return
	}

	// Create websocket Client
	wsClient := cws.NewClient(c)
	// clientID := wsClient.GetID()
	s.wsClients[wsClient.GetID()] = wsClient
	// Add websocket client to chat service
	// DEPRECATED because we use external chat
	// chatClient := s.chat.AddClient(clientID, wsClient)
	// chatClient.Route()
	log.Println("Initialized Chat")
	// TODO: Update packet
	// Add websocket client to app service
	log.Println("Initialized ServiceClient")

	s.initClientData(wsClient)
	go func(browserClient *cws.Client) {
		browserClient.Listen()
		log.Println("Closing connection")
		// chatClient.Close()
		browserClient.Close()
		log.Println("Closed connection")
	}(wsClient)
}

func (s *Server) initClientData(client *cws.Client) {
	s.chat.SendChatHistory(client.GetID())
	apps, err := s.GetApps()
	if err != nil {
		apps = []appDiscoveryMeta{}
	}
	data := initData{
		CurAppID: s.appID,
		App:      s.appMeta,
		Apps:     apps,
	}
	jsonData, err := json.Marshal(data)
	if err != nil {
		return
	}
	fmt.Println("Send Client INIT")
	client.Send(cws.WSPacket{
		Type: "INIT",
		Data: string(jsonData),
	}, nil)
}

func (s *Server) updateClientApps(client *cws.Client, updatedApps []appDiscoveryMeta) {
	data, _ := json.Marshal(updatedApps)
	client.Send(cws.WSPacket{
		Type: "UPDATEAPPLIST",
		Data: string(data),
	}, nil)
}

func (s *Server) registerIfMissing(updatedApps []appDiscoveryMeta) {
	for _, app := range updatedApps {
		if app.Addr == s.appMeta.Addr {
			return
		}
	}
	log.Println("Server is not found in Discovery. Re-Register")
	s.RegisterApp(s.appMeta)
}

func (s *Server) ListenAppListUpdate() {
	for updatedApps := range s.AppListUpdate() {
		log.Println("Get updated apps: ", updatedApps, s.wsClients)
		for _, client := range s.wsClients {
			s.updateClientApps(client, updatedApps)
		}
		s.registerIfMissing(updatedApps)
	}
}

func NewServer() *Server {
	cfg, err := config.ReadConfig(configFilePath)
	if err != nil {
		panic(err)
	}
	log.Printf("Config: %+v", cfg)

	server := &Server{
		wsClients:        map[string]*cws.Client{},
		discoveryHandler: NewDiscovery(cfg.DiscoveryHost),
	}

	r := mux.NewRouter()
	r.HandleFunc("/wscloudmorph", server.WS)
	r.HandleFunc("/echo", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Access-Control-Allow-Origin", "*")
	})
	if cfg.DiscoveryHost != "" {
		r.HandleFunc("/apps", server.GetAppsHandler)
	}
	r.PathPrefix("/static/").Handler(http.StripPrefix("/static/", http.FileServer(http.Dir("./web"))))
	r.HandleFunc("/embed",
		func(w http.ResponseWriter, r *http.Request) {
			tmpl, err := template.ParseFiles(embedPage)
			if err != nil {
				log.Fatal(err)
			}

			tmpl.Execute(w, nil)
		},
	)
	svmux := &http.ServeMux{}

	// Spawn a separated server running CloudApp
	log.Println("Spawn cloudapp server")
	cappServer := cloudapp.NewServerWithHTTPServerMux(cfg, r, svmux)
	server.cappServer = cappServer
	cappServer.Handle()

	r.PathPrefix("/").HandlerFunc(
		func(w http.ResponseWriter, r *http.Request) {
			tmpl, err := template.ParseFiles(indexPage)
			if err != nil {
				log.Fatal(err)
			}
			if err := tmpl.Execute(w, cfg); err != nil {
				log.Fatal(err)
			}
		},
	)

	svmux.Handle("/", r)
	// go cappServer.ListenAndServe()

	httpServer := &http.Server{
		Addr:         addr,
		ReadTimeout:  5 * time.Second,
		WriteTimeout: 5 * time.Second,
		IdleTimeout:  120 * time.Second,
		Handler:      svmux,
	}
	server.httpServer = httpServer

	server.chat = textchat.NewTextChat()
	appMeta := appDiscoveryMeta{
		Addr:         cfg.InstanceAddr,
		AppName:      cfg.AppName,
		AppMode:      cfg.AppMode,
		HasChat:      cfg.HasChat,
		PageTitle:    cfg.PageTitle,
		ScreenWidth:  cfg.ScreenWidth,
		ScreenHeight: cfg.ScreenHeight,
	}
	fmt.Println("appMeta", appMeta)

	appID, err := server.RegisterApp(appMeta)
	if err != nil {
		log.Println(err)
	}
	server.appID = appID
	server.appMeta = appMeta
	log.Println("Registered with AppID", server.appID)

	if cfg.DiscoveryHost != "" {
		go server.ListenAppListUpdate()
	}
	return server
}

func (o *Server) Shutdown() {
	err := o.RemoveApp(o.appID)
	if err != nil {
		log.Println(err)
	}
}

func (o *Server) Handle() {
	// Spawn Chat Handle
	go o.chat.Handle()
}

func (o *Server) ListenAndServe() error {
	log.Println("Server is running at", addr)
	return o.httpServer.ListenAndServe()
}

func monitor() {
	monitoringServerMux := http.NewServeMux()

	srv := http.Server{
		Addr:    fmt.Sprintf(":%d", 3535),
		Handler: monitoringServerMux,
	}
	log.Println("Starting monitoring server at", srv.Addr)

	pprofPath := fmt.Sprintf("/debug/pprof")
	log.Println("Profiling is enabled at", srv.Addr+pprofPath)
	monitoringServerMux.Handle(pprofPath+"/", http.HandlerFunc(pprof.Index))
	monitoringServerMux.Handle(pprofPath+"/cmdline", http.HandlerFunc(pprof.Cmdline))
	monitoringServerMux.Handle(pprofPath+"/profile", http.HandlerFunc(pprof.Profile))
	monitoringServerMux.Handle(pprofPath+"/symbol", http.HandlerFunc(pprof.Symbol))
	monitoringServerMux.Handle(pprofPath+"/trace", http.HandlerFunc(pprof.Trace))
	// pprof handler for custom pprof path needs to be explicitly specified, according to: https://github.com/gin-contrib/pprof/issues/8 . Don't know why this is not fired as ticket
	// https://golang.org/src/net/http/pprof/pprof.go?s=7411:7461#L305 only render index page
	monitoringServerMux.Handle(pprofPath+"/allocs", pprof.Handler("allocs"))
	monitoringServerMux.Handle(pprofPath+"/block", pprof.Handler("block"))
	monitoringServerMux.Handle(pprofPath+"/goroutine", pprof.Handler("goroutine"))
	monitoringServerMux.Handle(pprofPath+"/heap", pprof.Handler("heap"))
	monitoringServerMux.Handle(pprofPath+"/mutex", pprof.Handler("mutex"))
	monitoringServerMux.Handle(pprofPath+"/threadcreate", pprof.Handler("threadcreate"))
	go srv.ListenAndServe()

}

func main() {
	// HTTP server
	// TODO: Make the communication over websocket
	http.Handle("/assets/", http.StripPrefix("/assets", http.FileServer(http.Dir("./assets"))))
	monitor()
	server := NewServer()
	server.Handle()

	go func() {
		err := server.ListenAndServe()
		if err != nil {
			log.Fatal(err)
		}
	}()

	stop := make(chan os.Signal, 1)
	signal.Notify(stop, os.Interrupt)
	select {
	case <-stop:
		log.Println("Received SIGTERM, Quiting")
		server.Shutdown()
	}
}

// Encode encodes the input in base64
// It can optionally zip the input before encoding
func Encode(obj interface{}) string {
	b, err := json.Marshal(obj)
	if err != nil {
		panic(err)
	}

	return base64.StdEncoding.EncodeToString(b)
}

// Decode decodes the input from base64
// It can optionally unzip the input after decoding
func Decode(in string, obj interface{}) {
	b, err := base64.StdEncoding.DecodeString(in)
	if err != nil {
		panic(err)
	}

	err = json.Unmarshal(b, obj)
	if err != nil {
		panic(err)
	}
}

func NewDiscovery(discoveryHost string) *discoveryHandler {
	return &discoveryHandler{
		httpClient: &http.Client{
			Timeout: time.Second * 10,
		},
		discoveryHost: discoveryHost,
	}
}

func (s *Server) GetAppsHandler(w http.ResponseWriter, r *http.Request) {
	apps, err := s.GetApps()
	if err != nil {
		log.Println(err)
	}

	appsJSON, _ := json.Marshal(apps)
	packet := ws.Packet{
		PType: "UPDATEAPPLIST",
		Data:  string(appsJSON),
	}

	packetBytes, _ := json.Marshal(packet)
	w.Write(packetBytes)
}

func (s *Server) GetApps() ([]appDiscoveryMeta, error) {
	return s.discoveryHandler.GetApps()
}

func (s *Server) RegisterApp(meta appDiscoveryMeta) (string, error) {
	return s.discoveryHandler.Register(meta)
}

func (s *Server) RemoveApp(appID string) error {
	return s.discoveryHandler.Remove(s.appID)
}

func (s *Server) AppListUpdate() chan []appDiscoveryMeta {
	return s.discoveryHandler.AppListUpdate()
}

func (d *discoveryHandler) GetApps() ([]appDiscoveryMeta, error) {
	type GetAppsResponse struct {
		Apps []appDiscoveryMeta `json:"apps"`
	}
	var resp GetAppsResponse

	rawResp, err := d.httpClient.Get(d.discoveryHost + "/get-apps")
	if err != nil {
		return []appDiscoveryMeta{}, err
	}
	defer func() {
		rawResp.Body.Close()
	}()

	json.NewDecoder(rawResp.Body).Decode(&resp)

	return resp.Apps, nil
}

func (d *discoveryHandler) isNeedAppListUpdate(newApps []appDiscoveryMeta) bool {
	if len(newApps) != len(d.apps) {
		return true
	}

	for i, app := range newApps {
		if app != d.apps[i] {
			return true
		}
	}

	return false
}

func (d *discoveryHandler) AppListUpdate() chan []appDiscoveryMeta {
	updatedApps := make(chan []appDiscoveryMeta, 1)
	go func() {
		// TODO: Change to subscription based
		for range time.Tick(5 * time.Second) {
			newApps, err := d.GetApps()
			if err != nil {
				log.Println(err)
				continue
			}
			if d.isNeedAppListUpdate(newApps) {
				log.Println("Update AppHosts: ", newApps)
				updatedApps <- newApps
				d.apps = make([]appDiscoveryMeta, len(newApps))
				copy(d.apps, newApps)
			}
		}
	}()

	return updatedApps
}

func (d *discoveryHandler) Register(meta appDiscoveryMeta) (string, error) {
	reqBytes, err := json.Marshal(meta)
	if err != nil {
		return "", nil
	}

	resp, err := d.httpClient.Post(d.discoveryHost+"/register", "application/json", bytes.NewBuffer(reqBytes))
	if err != nil {
		return "", fmt.Errorf("Failed to register app. Err: %s", err.Error())
	}
	defer func() {
		resp.Body.Close()
	}()
	var appID string
	err = json.NewDecoder(resp.Body).Decode(&appID)
	if err != nil {
		return "", nil
	}

	return appID, nil
}

func (d *discoveryHandler) Remove(appID string) error {
	reqBytes, err := json.Marshal(appID)
	if err != nil {
		return nil
	}

	resp, err := d.httpClient.Post(d.discoveryHost+"/remove", "application/json", bytes.NewBuffer(reqBytes))
	if err != nil {
		return nil
	}
	resp.Body.Close()

	return err
}
