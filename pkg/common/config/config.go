package config

import (
	"errors"
	"io/ioutil"
	"net"

	"github.com/giongto35/cloud-morph/pkg/common/servercfg"
	"gopkg.in/yaml.v2"
)

type Config struct {
	Path    string `yaml:"path"`
	AppFile string `yaml:"appFile"`
	// To help WinAPI search the app
	WindowTitle  string `yaml:"windowTitle"`
	HWKey        bool   `yaml:"hardwareKey"`
	AppMode      string `yaml:"appMode"`
	AppName      string `yaml:"appName"`
	ScreenWidth  int    `yaml:"screenWidth"`
	ScreenHeight int    `yaml:"screenHeight"`
	IsWindowMode *bool  `yaml:"isWindowMode"`
	// Discovery service
	DiscoveryHost string `yaml:"discoveryHost"`
	InstanceAddr  string `yaml:"instanceAddr"`
	// Frontend plugin
	HasChat   bool   `yaml:"hasChat"`
	PageTitle string `yaml:"pageTitle"`
	// WebRTC config
	StunTurn string `yaml:"stunturn"` // Optional, Default: Google STUN
}

func ReadConfig(path string) (Config, error) {
	cfgyml, err := ioutil.ReadFile(path)
	if err != nil {
		return Config{}, err
	}

	cfg := Config{}
	err = yaml.Unmarshal(cfgyml, &cfg)

	if cfg.AppName == "" {
		cfg.AppName = cfg.WindowTitle
	}
	if cfg.StunTurn == "" {
		cfg.StunTurn = servercfg.DefaultSTUNTURN
	}
	if cfg.ScreenWidth == 0 {
		cfg.ScreenWidth = 800
	}
	if cfg.ScreenHeight == 0 {
		cfg.ScreenHeight = 600
	}
	if cfg.IsWindowMode == nil {
		boolTrue := true
		cfg.IsWindowMode = &boolTrue
	}
	if cfg.InstanceAddr == "" {
		ip, _ := getLocalIP()
		cfg.InstanceAddr = ip.String()
	}
	return cfg, err
}

func getLocalIP() (net.IP, error) {
	tt, err := net.Interfaces()
	if err != nil {
		return nil, err
	}
	for _, t := range tt {
		aa, err := t.Addrs()
		if err != nil {
			return nil, err
		}
		for _, a := range aa {
			ipnet, ok := a.(*net.IPNet)
			if !ok {
				continue
			}
			v4 := ipnet.IP.To4()
			if v4 == nil || v4[0] == 127 { // loopback address
				continue
			}
			return v4, nil
		}
	}
	return nil, errors.New("cannot find local IP address")
}
