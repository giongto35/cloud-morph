package cloudgame

import (
	"encoding/json"
	"log"
	"net/http"
	"time"

	"github.com/pion/rtp"
)

const (
	// CollaborativeMode Multiple users share the same app session
	CollaborativeMode = "collaborative"
	// OnDemandMode Multiple users runs on a new available machine
	OnDemandMode = "ondemand"
)

type Service struct {
	appModeHandler   *appModeHandler
	discoveryHandler *discoveryHandler
	ccApp            CloudGameClient
}

type AppHost struct {
	Host string `json:"host"`
}

type Config struct {
	Path    string `yaml:"path"`
	AppFile string `yaml:"appFile"`
	// To help WinAPI search the app
	WidowTitle string `yaml:"windowTitle"`
	HWKey      bool   `yaml:"hardwareKey"`
	AppMode    string `yaml:"appMode"`
	// Discovery service
	DiscoveryHost string `yaml:"discoveryHost"`
}

type instance struct {
	addr string
}

type appModeHandler struct {
	appMode            string
	availableInstances []instance
}

type discoveryHandler struct {
	httpClient    *http.Client
	discoveryHost string
}

func NewAppMode(appMode string) *appModeHandler {
	return &appModeHandler{
		appMode: appMode,
	}
}

func (d *discoveryHandler) GetAppHosts() []AppHost {
	type GetAppHostsResponse struct {
		appHosts []AppHost `json:"appHosts"`
	}
	var resp GetAppHostsResponse

	rawResp, err := d.httpClient.Get(d.discoveryHost + "/get-apps")
	if err != nil {
		// log.Warn(err)
		log.Fatal(err)
	}

	defer rawResp.Body.Close()
	json.NewDecoder(rawResp.Body).Decode(&resp)

	return resp.appHosts
}

func NewDiscovery(discoveryHost string) *discoveryHandler {
	return &discoveryHandler{
		httpClient: &http.Client{
			Timeout: time.Second * 10,
		},
		discoveryHost: discoveryHost,
	}
}

func (s *Service) GetAppHosts() []AppHost {
	return s.discoveryHandler.GetAppHosts()
}

// func NewCloudGameClient(cfg Config, gameEvents chan WSPacket) *ccImpl {
func NewCloudService(cfg Config, gameEvents chan WSPacket) *Service {
	return &Service{
		appModeHandler:   NewAppMode(cfg.AppMode),
		discoveryHandler: NewDiscovery(cfg.DiscoveryHost),
		ccApp:            NewCloudGameClient(cfg, gameEvents),
	}
}

func (s *Service) VideoStream() chan rtp.Packet {
	return s.ccApp.VideoStream()
}

func (s *Service) SendInput(packet WSPacket) {
	s.ccApp.SendInput(packet)
}

func (s *Service) GetSSRC() uint32 {
	return s.ccApp.GetSSRC()
}

func (s *Service) Handle() {
	s.ccApp.Handle()
}
