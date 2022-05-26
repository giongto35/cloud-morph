package cloudapp

import (
	"encoding/json"
	"log"
	"sync"
	"time"

	"github.com/giongto35/cloud-morph/pkg/common/config"
	"github.com/giongto35/cloud-morph/pkg/common/cws"
	"github.com/giongto35/cloud-morph/pkg/core/go/cloudapp/webrtc"
	"github.com/pion/rtp"
)

const (
	// CollaborativeMode Multiple users share the same app session
	CollaborativeMode = "collaborative"
	// OnDemandMode Multiple users runs on a new available machine
	OnDemandMode = "ondemand"
)

type Service struct {
	clients        map[string]*Client
	appModeHandler *appModeHandler
	ccApp          CloudAppClient
	config         config.Config
	// chat           *textchat.TextChat Not using own chat
	// communicate with cloud app
	appEvents  chan Packet
	webrtcConf *webrtc.Config
}

type Client struct {
	clientID    string
	ws          *cws.Client
	rtcConn     *webrtc.WebRTC
	videoStream chan *rtp.Packet
	audioStream chan *rtp.Packet
	appEvents   chan Packet
	// videoTrack   *webrtc.Track
	// cancel to trigger cleaning up when client is disconnected
	cancel chan struct{}
	// done to notify if the client is done clean up
	done       chan struct{}
	webrtcConf *webrtc.Config
}

type AppHost struct {
	// Host string `json:"host"`
	Addr    string `json:"addr"`
	AppName string `json:"app_name"`
}

type instance struct {
	addr string
}

type appModeHandler struct {
	appMode            string
	availableInstances []instance
}

func NewAppMode(appMode string) *appModeHandler {
	return &appModeHandler{
		appMode: appMode,
	}
}

// Heartbeat maintains connection to server
func (c *Client) Heartbeat() {
	// send heartbeat every 1s
	timer := time.Tick(time.Second)

	for range timer {
		select {
		case <-c.cancel:
			log.Println("Close heartbeat")
			return
		default:
		}
		// c.Send({PType: "heartbeat"})
	}
}

func (s *Service) AddClient(clientID string, ws *cws.Client) *Client {
	client := NewServiceClient(clientID, ws, s.appEvents, s.webrtcConf)
	s.clients[clientID] = client
	return client
}

func (s *Service) RemoveClient(clientID string) {
	client := s.clients[clientID]
	close(client.cancel)
	<-client.done
	if client.rtcConn != nil {
		client.rtcConn.StopClient()
		client.rtcConn = nil
	}
}

func NewServiceClient(clientID string, ws *cws.Client, appEvents chan Packet, conf *webrtc.Config) *Client {
	// The 1st packet
	ws.Send(cws.WSPacket{Type: "init", Data: conf.GetStun()}, nil)

	return &Client{
		appEvents:   appEvents,
		clientID:    clientID,
		ws:          ws,
		videoStream: make(chan *rtp.Packet, 100),
		audioStream: make(chan *rtp.Packet, 100),
		cancel:      make(chan struct{}),
		done:        make(chan struct{}),
		webrtcConf:  conf,
	}
}

func (c *Client) Handle() {
	defer func() {
		if r := recover(); r != nil {
			log.Println("Recovered when sent to close Image Channel")
		}
	}()

	wg := sync.WaitGroup{}

	// Video Stream
	wg.Add(1)
	go func() {
		defer func() {
			if r := recover(); r != nil {
				log.Println("Recovered. Maybe we :sent to Closed Channel", r)
				wg.Done()
			}
		}()

	loop:
		for packet := range c.videoStream {
			select {
			case <-c.cancel:
				break loop
			case c.rtcConn.ImageChannel <- packet:
			}
		}
		wg.Done()
		log.Println("Closed Service Video Channel")
	}()

	// Audio Stream
	wg.Add(1)
	go func() {
		defer func() {
			if r := recover(); r != nil {
				log.Println("Recovered. Maybe we :sent to Closed Channel", r)
				wg.Done()
			}
		}()

	loop:
		for packet := range c.audioStream {
			select {
			case <-c.cancel:
				break loop
			case c.rtcConn.AudioChannel <- packet:
			}
		}
		wg.Done()
		log.Println("Closed Service Audio Channel")
	}()

	// Input stream is closed after StopClient . TODO: check if can close earlier
	// wg.Add(1)
	go func() {
		// Data channel input
		for rawInput := range c.rtcConn.InputChannel {
			// TODO: No dynamic allocation
			wspacket := cws.WSPacket{}
			err := json.Unmarshal(rawInput, &wspacket)
			if err != nil {
				log.Println(err)
			}
			c.appEvents <- convertWSPacket(wspacket)
		}
		// wg.Done()
	}()
	wg.Wait()
	close(c.done)
}

func (c *Client) Route() {
	// Listen from video stream
	// WebRTC
	c.ws.Receive("initwebrtc", func(req cws.WSPacket) (resp cws.WSPacket) {
		log.Println("Received a request to createOffer from browser", req)

		c.rtcConn = webrtc.NewWebRTC()

		localSession, err := c.rtcConn.StartClient(
			func(candidate string) {
				// send back candidate string to browser
				c.ws.Send(cws.WSPacket{Type: "candidate", Data: candidate, SessionID: req.SessionID}, nil)
			},
			c.webrtcConf,
		)

		if err != nil {
			log.Println("Error: Cannot create new webrtc session", err)
			return cws.EmptyPacket
		}

		return cws.WSPacket{Type: "offer", Data: localSession}
	})

	c.ws.Receive(
		"answer",
		func(resp cws.WSPacket) (req cws.WSPacket) {
			log.Println("Received answer SDP from browser", resp)
			err := c.rtcConn.SetRemoteSDP(resp.Data)
			if err != nil {
				log.Println("Error: Cannot set RemoteSDP of client: " + resp.SessionID)
			}

			go c.Handle()
			return cws.EmptyPacket
		},
	)

	c.ws.Receive(
		"candidate",
		func(resp cws.WSPacket) (req cws.WSPacket) {
			log.Println("Received remote Ice Candidate from browser")

			err := c.rtcConn.AddCandidate(resp.Data)
			if err != nil {
				log.Println("Error: Cannot add IceCandidate of client: " + resp.SessionID)
			}

			return cws.EmptyPacket
		},
	)
}

// NewCloudService returns a Cloud Service
func NewCloudService(conf config.Config) *Service {
	appEvents := make(chan Packet, 1)

	webrtcConf := &webrtc.DefaultConfig
	webrtcConf.Override(
		webrtc.Codec(conf.VideoCodec),
		webrtc.DisableInterceptors(conf.DisableInterceptors),
		webrtc.Nat1to1(conf.NAT1To1IP),
		webrtc.StunServer(conf.StunTurn),
	)

	s := &Service{
		clients:        map[string]*Client{},
		appEvents:      appEvents,
		appModeHandler: NewAppMode(conf.AppMode),
		ccApp:          NewCloudAppClient(conf, appEvents),
		config:         conf,
		webrtcConf:     webrtcConf,
	}

	return s
}

func (s *Service) SendInput(packet Packet) {
	s.ccApp.SendInput(packet)
}

func (s *Service) Handle() {
	go func() {
		defer func() {
			if r := recover(); r != nil {
				log.Println("Recovered when sent to closed Video Stream channel", r)
			}
		}()
		for p := range s.ccApp.VideoStream() {
			for id, client := range s.clients {
				select {
				case <-client.cancel:
					log.Println("Closing Video Audio")
					// stop producing for client
					delete(s.clients, id)
					close(client.audioStream)
					close(client.videoStream)
				case client.videoStream <- p:
				}
			}
		}
	}()
	go func() {
		defer func() {
			if r := recover(); r != nil {
				log.Println("Recovered when sent to closed Video Stream channel", r)
			}
		}()
		for p := range s.ccApp.AudioStream() {
			for _, client := range s.clients {
				select {
				// case <-client.cancel:
				// fmt.Println("Closing Audio")
				// stop producing for client
				// close(client.audioStream)
				case client.audioStream <- p:
				}
			}
		}
	}()
	s.ccApp.Handle()
}
