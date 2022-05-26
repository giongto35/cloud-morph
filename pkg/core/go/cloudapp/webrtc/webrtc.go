package webrtc

import (
	"encoding/base64"
	"encoding/json"
	"fmt"
	"log"
	"strings"
	"time"

	"github.com/gofrs/uuid"
	"github.com/pion/interceptor"
	"github.com/pion/rtp"
	"github.com/pion/webrtc/v3"
)

type WebRTC struct {
	ID string

	connection  *webrtc.PeerConnection
	isConnected bool
	isClosed    bool

	ImageChannel chan *rtp.Packet
	AudioChannel chan *rtp.Packet
	InputChannel chan []byte

	Done     bool
	lastTime time.Time
	curFPS   int
}

// Encode encodes the input in base64
func Encode(obj interface{}) (string, error) {
	b, err := json.Marshal(obj)
	if err != nil {
		return "", err
	}

	return base64.StdEncoding.EncodeToString(b), nil
}

// Decode decodes the input from base64
func Decode(in string, obj interface{}) error {
	b, err := base64.StdEncoding.DecodeString(in)
	if err != nil {
		return err
	}

	err = json.Unmarshal(b, obj)
	if err != nil {
		return err
	}

	return nil
}

// NewWebRTC create
func NewWebRTC() *WebRTC {
	w := &WebRTC{
		ID: uuid.Must(uuid.NewV4()).String(),

		ImageChannel: make(chan *rtp.Packet, 100),
		AudioChannel: make(chan *rtp.Packet, 100),
		InputChannel: make(chan []byte, 100),
	}
	return w
}

// StartClient start webrtc
func (w *WebRTC) StartClient(onIceCandidate func(c string), conf *Config) (string, error) {
	defer func() {
		if err := recover(); err != nil {
			log.Println(err)
			w.StopClient()
		}
	}()
	var err error
	var videoTrack *webrtc.TrackLocalStaticRTP

	// reset client
	if w.isConnected {
		w.StopClient()
		time.Sleep(2 * time.Second)
	}

	log.Println("=== StartClient ===")
	w.connection, err = NewPeerConnection(conf)
	if err != nil {
		return "", err
	}

	// add video track
	videoTrack, err = webrtc.NewTrackLocalStaticRTP(webrtc.RTPCodecCapability{MimeType: conf.VideoCodec}, "video", "pion")

	if err != nil {
		return "", err
	}

	_, err = w.connection.AddTrack(videoTrack)
	if err != nil {
		return "", err
	}
	log.Println("Add video track")

	// add audio track
	opusTrack, err := webrtc.NewTrackLocalStaticRTP(webrtc.RTPCodecCapability{MimeType: webrtc.MimeTypeOpus}, "audio", "pion")
	if err != nil {
		return "", err
	}
	_, err = w.connection.AddTrack(opusTrack)
	if err != nil {
		return "", err
	}

	_, err = w.connection.AddTransceiverFromKind(webrtc.RTPCodecTypeAudio, webrtc.RtpTransceiverInit{Direction: webrtc.RTPTransceiverDirectionRecvonly})

	// create data channel for input, and register callbacks
	// order: true, negotiated: false, id: random
	inputTrack, err := w.connection.CreateDataChannel("app-input", nil)

	inputTrack.OnOpen(func() {
		log.Printf("Data channel '%s'-'%d' open.\n", inputTrack.Label(), inputTrack.ID())
	})

	// Register text message handling
	inputTrack.OnMessage(func(msg webrtc.DataChannelMessage) {
		// TODO: Can add recover here
		w.InputChannel <- msg.Data
	})

	inputTrack.OnClose(func() {
		log.Println("Data channel closed")
		log.Println("Closed webrtc")
	})

	// WebRTC state callback
	w.connection.OnICEConnectionStateChange(func(connectionState webrtc.ICEConnectionState) {
		log.Printf("ICE Connection State has changed: %s\n", connectionState.String())
		if connectionState == webrtc.ICEConnectionStateConnected {
			go func() {
				w.isConnected = true
				log.Println("ConnectionStateConnected")
				w.startStreaming(videoTrack, opusTrack)
			}()

		}
		if connectionState == webrtc.ICEConnectionStateFailed || connectionState == webrtc.ICEConnectionStateClosed || connectionState == webrtc.ICEConnectionStateDisconnected {
			log.Println("ICE Connection failed")
			w.StopClient()
		}
	})

	w.connection.OnICECandidate(func(iceCandidate *webrtc.ICECandidate) {
		if iceCandidate != nil {
			log.Println("OnIceCandidate:", iceCandidate.ToJSON().Candidate)
			candidate, err := Encode(iceCandidate.ToJSON())
			if err != nil {
				log.Println("Encode IceCandidate failed: " + iceCandidate.ToJSON().Candidate)
				return
			}
			onIceCandidate(candidate)
		} else {
			// finish, send null
			onIceCandidate("")
		}
	})

	// Stream provider supposes to send offer
	offer, err := w.connection.CreateOffer(nil)
	if err != nil {
		return "", err
	}
	log.Println("Created Offer")

	err = w.connection.SetLocalDescription(offer)
	if err != nil {
		return "", err
	}

	localSession, err := Encode(offer)
	if err != nil {
		return "", err
	}

	return localSession, nil
}

func (w *WebRTC) SetRemoteSDP(remoteSDP string) error {
	var answer webrtc.SessionDescription
	err := Decode(remoteSDP, &answer)
	if err != nil {
		log.Println("Decode remote sdp from peer failed")
		return err
	}

	fmt.Println("Wconnection", w.connection)
	err = w.connection.SetRemoteDescription(answer)
	if err != nil {
		log.Println("Set remote description from peer failed")
		return err
	}

	log.Println("Set Remote Description")
	return nil
}

func (w *WebRTC) AddCandidate(candidate string) error {
	var iceCandidate webrtc.ICECandidateInit
	err := Decode(candidate, &iceCandidate)
	if err != nil {
		log.Println("Decode Ice candidate from peer failed")
		return err
	}
	log.Println("Decoded Ice: " + iceCandidate.Candidate)

	err = w.connection.AddICECandidate(iceCandidate)
	if err != nil {
		log.Println("Add Ice candidate from peer failed")
		return err
	}

	log.Println("Add Ice Candidate: " + iceCandidate.Candidate)
	return nil
}

// StopClient disconnect
func (w *WebRTC) StopClient() {
	defer func() {
		if r := recover(); r != nil {
			fmt.Println("Recovered from err. Maybe we closed a closed channel", r)
		}
	}()
	// if stopped, bypass
	// if w.isConnected == false {
	// 	return
	// }

	log.Println("===StopClient===")
	if w.connection != nil {
		log.Println("WebRTC Connection close")
		w.connection.Close()
		w.connection = nil
	}
	// w.isConnected = false
	log.Println("Close Input channel")
	close(w.InputChannel)
	// webrtc is producer, so we close
	// NOTE: ImageChannel is waiting for input. Close in writer is not correct for this
	close(w.ImageChannel)
	close(w.AudioChannel)
}

// IsConnected comment
func (w *WebRTC) IsConnected() bool {
	return w.isConnected
}

func (w *WebRTC) startStreaming(videoTrack *webrtc.TrackLocalStaticRTP, opusTrack *webrtc.TrackLocalStaticRTP) {
	log.Println("Start streaming")
	// receive frame buffer
	go func() {
		for packet := range w.ImageChannel {
			if writeErr := videoTrack.WriteRTP(packet); writeErr != nil {
				panic(writeErr)
			}
		}
	}()

	// send audio
	go func() {
		defer func() {
			if r := recover(); r != nil {
				fmt.Println("Recovered from err", r)
			}
		}()

		for packet := range w.AudioChannel {
			if writeErr := opusTrack.WriteRTP(packet); writeErr != nil {
				panic(writeErr)
			}
		}
	}()
}

func NewPeerConnection(conf *Config) (*webrtc.PeerConnection, error) {
	m := &webrtc.MediaEngine{}
	if err := m.RegisterDefaultCodecs(); err != nil {
		return nil, err
	}

	i := &interceptor.Registry{}
	if !conf.DisableInterceptors {
		if err := webrtc.RegisterDefaultInterceptors(m, i); err != nil {
			return nil, err
		}
	}

	s := webrtc.SettingEngine{}
	if conf.Nat1to1 != "" {
		if ip, ct, err := parseNatCandidate(conf.Nat1to1); err == nil {
			s.SetNAT1To1IPs(ip, ct)
			log.Printf("Using 1:1 NAT %s", conf.Nat1to1)
		} else {
			log.Printf("NAT map error: %v", err)
		}
	}

	api := webrtc.NewAPI(webrtc.WithMediaEngine(m), webrtc.WithInterceptorRegistry(i), webrtc.WithSettingEngine(s))
	return api.NewPeerConnection(conf.Configuration)
}

func parseNatCandidate(v string) (ips []string, candidateType webrtc.ICECandidateType, err error) {
	parts := strings.Split(v, "/")
	if len(parts) < 2 {
		return nil, 0, fmt.Errorf("wrong ICE IP NAT mapping format, %v", parts)
	}
	ips = []string{parts[0]}
	candidateType, err = webrtc.NewICECandidateType(parts[1])
	return
}
