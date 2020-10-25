package main

import (
	"bytes"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"html/template"
	"io/ioutil"
	"log"
	"net/http"
	"net/http/pprof"
	"os"
	"os/signal"
	"time"

	"github.com/giongto35/cloud-morph/pkg/addon/textchat"
	"github.com/giongto35/cloud-morph/pkg/common/config"
	"github.com/giongto35/cloud-morph/pkg/common/ws"
	"github.com/giongto35/cloud-morph/pkg/core/go/cloudgame"
	"github.com/gofrs/uuid"
	"github.com/gorilla/mux"
	"github.com/gorilla/websocket"
	"gopkg.in/yaml.v2"
)

var upgrader = websocket.Upgrader{}

const configFilePath = "config.yaml"

var curApp string = "Notepad"

const indexPage string = "web/index.html"
const addr string = ":8080"

var chatEventTypes []string = []string{"CHAT"}
var gameEventTypes []string = []string{"OFFER", "ANSWER", "MOUSEDOWN", "MOUSEUP", "MOUSEMOVE", "KEYDOWN", "KEYUP"}
var dscvEventTypes []string = []string{"SELECTHOST"}

// TODO: multiplex clientID
var clientID string

type Client struct {
	clientID string
	conn     *websocket.Conn
	routes   map[string]chan ws.Packet
}

type Server struct {
	appID            string
	httpServer       *http.Server
	clients          map[string]*Client
	cgame            *cloudgame.Service
	chat             *textchat.TextChat
	discoveryHandler *discoveryHandler
}

type discoveryHandler struct {
	httpClient    *http.Client
	discoveryHost string
	apps          []appDiscoveryMeta
}

type appDiscoveryMeta struct {
	ID        string `yaml:"id"`
	Addr      string `yaml:"addr"`
	AppMode   string `yaml:"app_mode"`
	HasChat   bool   `yaml:"has_chat"`
	PageTitle string `yaml:"page_title"`
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

	// Generate clientID for browserClient
	for {
		clientID = uuid.Must(uuid.NewV4()).String()
		// check duplicate
		if _, ok := s.clients[clientID]; !ok {
			break
		}
	}

	// Create browserClient instance
	client := NewClient(c, clientID)
	s.clients[clientID] = client
	// Add client to chat management
	chatClient := s.chat.AddClient(clientID, client.conn)
	client.Route(chatEventTypes, chatClient.WSEvents)
	s.chat.SendChatHistory(clientID)
	fmt.Println("Initialized Chat")
	// TODO: Update packet
	// Run browser listener first (to capture ping)
	serviceClient := s.cgame.AddClient(clientID, client.conn)
	client.Route(gameEventTypes, serviceClient.WSEvents)
	fmt.Println("Initialized ServiceClient")
	go s.ListenAppListUpdate()

	go func(client *Client) {
		client.Listen()
		chatClient.Close()
		serviceClient.Close()
		delete(s.clients, clientID)
	}(client)
}

func (s *Server) ListenAppListUpdate() {
	for updatedApps := range s.AppListUpdate() {
		log.Println("Get updated apps: ", updatedApps, s.clients)
		for _, client := range s.clients {
			data, _ := json.Marshal(updatedApps)
			client.Send(ws.Packet{
				PType: "UPDATEAPPLIST",
				Data:  string(data),
			})
		}
	}
}

func (c *Client) Route(ptypes []string, ch chan ws.Packet) {
	for _, t := range ptypes {
		c.routes[t] = ch
	}
}

func (c *Client) Listen() {
	defer func() {
		if c.conn != nil {
			c.conn.Close()
			c.conn = nil
		}
	}()

	for {
		_, rawMsg, err := c.conn.ReadMessage()
		if err != nil {
			log.Println("[!] read:", err)
			// TODO: Check explicit disconnect error to break
			break
		}
		wspacket := ws.Packet{}
		err = json.Unmarshal(rawMsg, &wspacket)
		rChan, ok := c.routes[wspacket.PType]
		if !ok {
			continue
		}

		rChan <- wspacket
	}
}

func (c *Client) Send(packet ws.Packet) {
	data, err := json.Marshal(packet)
	if err != nil {
		return
	}

	c.conn.WriteMessage(websocket.TextMessage, data)
}

func NewClient(c *websocket.Conn, clientID string) *Client {
	return &Client{
		clientID: clientID,
		conn:     c,
		routes:   make(map[string]chan ws.Packet, 1),
	}
}

func NewServer() *Server {
	cfg, err := readConfig(configFilePath)
	if err != nil {
		panic(err)
	}

	server := &Server{
		clients:          map[string]*Client{},
		discoveryHandler: NewDiscovery(cfg.DiscoveryHost),
	}

	// templateData := TemplateData{
	// 	Chat:          cfg.HasChat,
	// 	PageTitle:     cfg.PageTitle,
	// 	Collaborative: cfg.AppMode == "collaborative",
	// }

	r := mux.NewRouter()
	r.HandleFunc("/ws", server.WS)
	r.PathPrefix("/static/").Handler(http.StripPrefix("/static/", http.FileServer(http.Dir("./web"))))
	r.PathPrefix("/").HandlerFunc(
		func(w http.ResponseWriter, r *http.Request) {
			tmpl, err := template.ParseFiles(indexPage)
			if err != nil {
				log.Fatal(err)
			}

			tmpl.Execute(w, nil)
		},
	)

	svmux := &http.ServeMux{}
	svmux.Handle("/", r)

	httpServer := &http.Server{
		Addr:         addr,
		ReadTimeout:  5 * time.Second,
		WriteTimeout: 5 * time.Second,
		IdleTimeout:  120 * time.Second,
		Handler:      svmux,
	}
	server.httpServer = httpServer
	log.Println("Spawn server")

	// Launch Game VM
	server.cgame = cloudgame.NewCloudService(cfg)
	server.chat = textchat.NewTextChat()
	appID, err := server.RegisterApp(appDiscoveryMeta{
		Addr:      addr,
		AppMode:   cfg.AppMode,
		HasChat:   cfg.HasChat,
		PageTitle: cfg.PageTitle,
	})
	server.appID = appID

	return server
}

func (o *Server) Shutdown() {
	fmt.Println("send remove")
	err := o.RemoveApp(o.appID)
	fmt.Println("Removed")
	if err != nil {
		fmt.Println(err)
	}
}

func readConfig(path string) (config.Config, error) {
	cfgyml, err := ioutil.ReadFile(path)
	if err != nil {
		return config.Config{}, err
	}

	cfg := config.Config{}
	err = yaml.Unmarshal(cfgyml, &cfg)

	if cfg.AppName == "" {
		cfg.AppName = cfg.WindowTitle
	}
	return cfg, err
}

func (o *Server) Handle() {
	// Spawn CloudGaming Handle
	go o.cgame.Handle()
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
		stop := make(chan os.Signal, 1)
		signal.Notify(stop, os.Interrupt)
		select {
		case <-stop:
			fmt.Println("Received SIGTERM, Quiting")
			server.Shutdown()
		}
	}()

	err := server.ListenAndServe()
	if err != nil {
		log.Fatal(err)
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

func (s *Server) GetApps() []appDiscoveryMeta {
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

func (d *discoveryHandler) GetApps() []appDiscoveryMeta {
	type GetAppsResponse struct {
		apps []appDiscoveryMeta `json:"apps"`
	}
	var resp GetAppsResponse

	rawResp, err := d.httpClient.Get(d.discoveryHost + "/get-apps")
	fmt.Println(rawResp)
	if err != nil {
		log.Println(err)
		return []appDiscoveryMeta{}
	}

	json.NewDecoder(rawResp.Body).Decode(&resp)

	return resp.apps
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
			fmt.Println("getting apps")
			newApps := d.GetApps()
			fmt.Println("newApps", newApps)
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
		return "", nil
	}
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

	_, err = d.httpClient.Post(d.discoveryHost+"/remove", "application/json", bytes.NewBuffer(reqBytes))
	if err != nil {
		return nil
	}

	return err

}
