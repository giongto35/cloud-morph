package cloudgame

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io/ioutil"
	"net/http"
	"time"

	"gopkg.in/yaml.v2"

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
	config           Config
}

type AppHost struct {
	// Host string `json:"host"`
	Addr    string `json:"addr"`
	AppName string `json:"app_name"`
}

type Config struct {
	Path    string `yaml:"path"`
	AppFile string `yaml:"appFile"`
	// To help WinAPI search the app
	WindowTitle string `yaml:"windowTitle"`
	HWKey       bool   `yaml:"hardwareKey"`
	AppMode     string `yaml:"appMode"`
	AppName     string `yaml:"appName"`
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
		AppHosts []AppHost `json:"apps"`
	}
	var resp GetAppHostsResponse

	rawResp, err := d.httpClient.Get(d.discoveryHost + "/get-apps")
	if err != nil {
		// log.Warn(err)
		fmt.Println(err)
	}

	defer rawResp.Body.Close()
	json.NewDecoder(rawResp.Body).Decode(&resp)

	return resp.AppHosts
}

func (d *discoveryHandler) Register(addr string, appName string) error {
	type RegisterAppRequest struct {
		Addr    string `json:"addr"`
		AppName string `json:"app_name"`
	}
	req := RegisterAppRequest{
		Addr:    addr,
		AppName: appName,
	}

	reqBytes, err := json.Marshal(req)
	if err != nil {
		return nil
	}

	_, err = d.httpClient.Post(d.discoveryHost+"/register", "application/json", bytes.NewBuffer(reqBytes))
	if err != nil {
		return nil
	}

	return err
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

func (s *Service) Register(addr string) error {
	return s.discoveryHandler.Register(addr, s.config.AppName)
}

func readConfig(path string) (Config, error) {
	cfgyml, err := ioutil.ReadFile(path)
	if err != nil {
		return Config{}, err
	}

	cfg := Config{}
	err = yaml.Unmarshal(cfgyml, &cfg)

	if cfg.AppName == "" {
		cfg.AppName = cfg.WindowTitle
	}
	return cfg, err
}

// func NewCloudGameClient(cfg Config, gameEvents chan WSPacket) *ccImpl {
func NewCloudService(configFilePath string, gameEvents chan WSPacket) *Service {
	cfg, err := readConfig(configFilePath)
	if err != nil {
		panic(err)
	}

	return &Service{
		appModeHandler:   NewAppMode(cfg.AppMode),
		discoveryHandler: NewDiscovery(cfg.DiscoveryHost),
		ccApp:            NewCloudGameClient(cfg, gameEvents),
		config:           cfg,
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
