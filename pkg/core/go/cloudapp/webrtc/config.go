package webrtc

import "github.com/pion/webrtc/v3"

type Config struct {
	webrtc.Configuration

	Nat1to1             string
	DisableInterceptors bool
	VideoCodec          string
}

var DefaultConfig = Config{
	Configuration: webrtc.Configuration{
		ICEServers: []webrtc.ICEServer{{URLs: []string{"stun:stun.l.google.com:19302"}}},
	},
	VideoCodec: webrtc.MimeTypeH264,
}

func (c *Config) GetStun() string {
	if len(c.Configuration.ICEServers) == 0 {
		return ""
	}
	// hello, npe
	return c.Configuration.ICEServers[0].URLs[0]
}

func (c *Config) Override(options ...Option) {
	for _, opt := range options {
		opt(c)
	}
}

type Option func(*Config)

func Codec(name string) Option {
	return func(c *Config) {
		var codec string
		switch name {
		case "h264":
			codec = webrtc.MimeTypeH264
		case "vpx":
			codec = webrtc.MimeTypeVP8
		default:
			codec = webrtc.MimeTypeH264
		}
		c.VideoCodec = codec
	}
}

func DisableInterceptors(disable bool) Option {
	return func(c *Config) { c.DisableInterceptors = disable }
}

func Nat1to1(natIp string) Option { return func(c *Config) { c.Nat1to1 = natIp } }

func StunServer(server string) Option {
	return func(c *Config) {
		var ice []webrtc.ICEServer
		if server == "" {
			return
		}
		if server == "none" {
			ice = []webrtc.ICEServer{}
		} else {
			ice = append(ice, webrtc.ICEServer{URLs: []string{server}})
		}
		c.Configuration.ICEServers = ice
	}
}
