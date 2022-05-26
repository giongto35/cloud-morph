// Widget server to serve a standalone cloudmorph instance
package cloudapp

import (
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"text/template"
	"time"

	"github.com/giongto35/cloud-morph/pkg/common/config"
	"github.com/giongto35/cloud-morph/pkg/common/cws"
	"github.com/gorilla/mux"
	"github.com/gorilla/websocket"
)

var upgrader = websocket.Upgrader{}

type initData struct {
	CurAppID string `json:"cur_app_id"`
	// App maynot be inside Apps because App can be in local, not in discovery
	App config.AppDiscoveryMeta `json:"cur_app"`
}

const embedPage string = "web/embed/embed.html"
const addr string = ":8080"

type Server struct {
	appID      string
	httpServer *http.Server
	wsClients  map[string]*cws.Client
	capp       *Service
	appMeta    config.AppDiscoveryMeta
}

func NewServer(cfg config.Config) *Server {
	r := mux.NewRouter()
	r.PathPrefix("/static/").Handler(http.StripPrefix("/static/", http.FileServer(http.Dir("./web"))))

	svmux := &http.ServeMux{}
	svmux.Handle("/", r)

	return NewServerWithHTTPServerMux(cfg, r, svmux)
}

func NewServerWithHTTPServerMux(cfg config.Config, r *mux.Router, svmux *http.ServeMux) *Server {
	server := &Server{}

	r.HandleFunc("/ws", server.WS)
	r.HandleFunc("/embed",
		func(w http.ResponseWriter, r *http.Request) {
			tmpl, err := template.ParseFiles(embedPage)
			if err != nil {
				log.Fatal(err)
			}

			tmpl.Execute(w, nil)
		},
	)
	fmt.Println("handler", r)

	httpServer := &http.Server{
		Addr:         addr,
		ReadTimeout:  5 * time.Second,
		WriteTimeout: 5 * time.Second,
		IdleTimeout:  120 * time.Second,
		Handler:      svmux,
	}
	log.Println("Embedded server")
	server.capp = NewCloudService(cfg)
	appMeta := config.AppDiscoveryMeta{
		Addr:         cfg.InstanceAddr,
		AppName:      cfg.AppName,
		AppMode:      cfg.AppMode,
		HasChat:      cfg.HasChat,
		PageTitle:    cfg.PageTitle,
		ScreenWidth:  cfg.ScreenWidth,
		ScreenHeight: cfg.ScreenHeight,
	}
	server.httpServer = httpServer
	server.appMeta = appMeta

	return server
}

func (o *Server) Handle() {
	// Spawn CloudGaming Handle
	go o.capp.Handle()
}

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
	clientID := wsClient.GetID()
	// TODO: Update packet
	// Add websocket client to app service
	serviceClient := s.capp.AddClient(clientID, wsClient)
	serviceClient.Route()
	log.Println("Initialized ServiceClient")

	s.initClientData(wsClient)
	go func(browserClient *cws.Client) {
		browserClient.Listen()
		log.Println("Closing connection")
		browserClient.Close()
		s.capp.RemoveClient(clientID)
		log.Println("Closed connection")
	}(wsClient)
}

func (s *Server) initClientData(client *cws.Client) {
	data := initData{
		CurAppID: s.appID,
		App:      s.appMeta,
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

func (o *Server) ListenAndServe() error {
	log.Println("Server is running at", addr)
	return o.httpServer.ListenAndServe()
}

func (o *Server) Shutdown() {
}
