package config

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
