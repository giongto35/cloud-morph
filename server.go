package main

import (
	"encoding/base64"
	"encoding/json"
	"fmt"
	"html/template"
	"io/ioutil"
	"log"
	"net/http"
	"net/http/pprof"
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

// TODO: multiplex clientID
var clientID string

type Client struct {
	clientID string
	conn     *websocket.Conn
	routes   map[string]chan ws.Packet
}

type Server struct {
	httpServer *http.Server
	clients    map[string]*Client
	cgame      *cloudgame.Service
	chat       *textchat.TextChat
}

type TemplateData struct {
	Chat          bool
	PageTitle     string
	Collaborative bool
}

// GetWeb returns web frontend
func (o *Server) GetWebWithData(templateData TemplateData) func(w http.ResponseWriter, r *http.Request) {
	return func(w http.ResponseWriter, r *http.Request) {
		tmpl, err := template.ParseFiles(indexPage)
		if err != nil {
			log.Fatal(err)
		}

		tmpl.Execute(w, templateData)
	}
}

//GetWeb(w http.ResponseWriter, r *http.Request) {
//tmpl, err := template.ParseFiles(indexPage)
//if err != nil {
//log.Fatal(err)
//}

//tmpl.Execute(w, templateData)
//}

// WSO handles all connections from user/frontend to coordinator
func (s *Server) WS(w http.ResponseWriter, r *http.Request) {
	log.Println("A user is connecting...")
	// defer func() {
	// 	if r := recover(); r != nil {
	// 		log.Println("Warn: Something wrong. Recovered in ", r)
	// 	}
	// }()

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

	go func(client *Client) {
		client.Listen()
		chatClient.Close()
		serviceClient.Close()
		delete(s.clients, clientID)
	}(client)
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

func NewClient(c *websocket.Conn, clientID string) *Client {
	return &Client{
		clientID: clientID,
		conn:     c,
		routes:   make(map[string]chan ws.Packet, 1),
	}
}

func NewServer() *Server {
	server := &Server{
		clients: map[string]*Client{},
	}

	cfg, err := readConfig(configFilePath)
	if err != nil {
		panic(err)
	}

	templateData := TemplateData{
		Chat:          cfg.HasChat,
		PageTitle:     cfg.PageTitle,
		Collaborative: cfg.AppMode == "collaborative",
	}

	r := mux.NewRouter()
	r.HandleFunc("/ws", server.WS)
	r.PathPrefix("/static/").Handler(http.StripPrefix("/static/", http.FileServer(http.Dir("./web"))))
	r.PathPrefix("/").HandlerFunc(server.GetWebWithData(templateData))

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

	return server
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
