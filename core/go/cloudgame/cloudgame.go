package cloudgame

import (
	"bytes"
	"encoding/json"
	"fmt"
	"log"
	"net"
	"os/exec"
	"syscall"
	"time"

	"github.com/pion/rtp"
	"github.com/pion/webrtc/v2"
)

type WSPacket struct {
	PType string `json:"type"`
	// TODO: Make Data generic: map[string]interface{} for more usecases
	Data string `json:"data"`
}

type InputEvent struct {
	inputType    bool
	inputPayload []byte
}

type CloudGameClient interface {
	VideoStream() chan rtp.Packet
	SendInput(WSPacket)
	// TODO: Remove it
	GetSSRC() uint32
}

type ccImpl struct {
	isReady     bool
	listener    *net.UDPConn
	videoStream chan rtp.Packet
	wineConn    *net.TCPConn
	ssrc        uint32
	payloadType uint8
}

const startRTPPort = 5004
const eventKeyDown = "KEYDOWN"
const eventMouse = "MOUSE"

var cuRTPPort = startRTPPort

type Config struct {
	Path       string `yaml:"path"`
	AppFile    string `yaml:"appFile"`
	WidowTitle string `yaml:"windowTitle"` // To help WinAPI search the app
}

func NewCloudGameClient(cfg Config) *ccImpl {
	c := &ccImpl{
		videoStream: make(chan rtp.Packet, 1),
	}

	la, err := net.ResolveTCPAddr("tcp4", ":9090")
	if err != nil {
		panic(err)
	}
	log.Println("listening wine at port 9090")
	ln, err := net.ListenTCP("tcp", la)
	if err != nil {
		panic(err)
	}

	c.launchGameVM(cuRTPPort, cfg.Path, cfg.AppFile, cfg.WidowTitle)
	log.Println("Launched application VM")

	// Read video stream from encoded video stream produced by FFMPEG
	listener, listenerssrc := c.newLocalStreamListener(cuRTPPort)
	c.listener = listener
	c.ssrc = listenerssrc

	c.listenVideoStream()
	log.Println("Launched Video stream listener")

	// Maintain input stream from server to Virtual Machine over websocket
	// Why Websocket: because normal IPC cannot communicate cross OS.
	go func() {
		for {
			// Polling Wine socket connection (input stream)
			conn, err := ln.AcceptTCP()
			if err != nil {
				// handle error
			}
			conn.SetKeepAlive(true)
			conn.SetKeepAlivePeriod(10 * time.Second)
			c.wineConn = conn
			// Successfully obtain input stream
			log.Println("Server is successfully lauched!")
			log.Println("Listening at :8080")
			c.isReady = true
			go c.healthCheckVM()
		}
	}()

	return c
}

func (c *ccImpl) GetSSRC() uint32 {
	return c.ssrc
}

// done to forcefully stop all processes
func (c *ccImpl) launchGameVM(rtpPort int, appPath string, appFile string, windowTitle string) chan struct{} {
	var cmd *exec.Cmd
	var streamCmd *exec.Cmd

	var out bytes.Buffer
	var stderr bytes.Buffer

	// go func() {
	// 	log.Println("Reading pipe stderr")
	// 	for {
	// 		log.Println(string(stderr.Bytes()))
	// 		time.Sleep(time.Second)
	// 	}
	// }()
	// go func() {
	// 	log.Println("Reading pipe stdout")
	// 	for {
	// 		log.Println(string(out.Bytes()))
	// 		time.Sleep(time.Second)
	// 	}
	// }()

	log.Println("execing run-client.sh")
	// cmd = exec.Command("./run-wine-nodocker.sh", appPath, appFile, windowTitle)
	cmd = exec.Command("./run-wine.sh", appPath, appFile, windowTitle)

	cmd.Stdout = &out
	cmd.Stderr = &stderr
	err := cmd.Run()
	if err != nil {
		panic(err)
	}
	log.Println("execed run-client.sh")

	done := make(chan struct{})
	// clean up func
	go func() {
		<-done
		err := streamCmd.Process.Kill()
		log.Println("Kill streamcmd: ", err)

		err = cmd.Process.Kill()
		log.Println("Kill game: ", err)

		log.Println("killing", streamCmd.Process.Pid)
		syscall.Kill(streamCmd.Process.Pid, syscall.SIGKILL)
	}()

	return done
}

// healthCheckVM to maintain connection
func (c *ccImpl) healthCheckVM() {
	for {
		c.wineConn.Write([]byte{0})
		time.Sleep(2 * time.Second)
	}
}

// newLocalStreamListener returns RTP: listener and SSRC of that listener
func (c *ccImpl) newLocalStreamListener(rtpPort int) (*net.UDPConn, uint32) {
	// Open a UDP Listener for RTP Packets on port 5004
	listener, err := net.ListenUDP("udp", &net.UDPAddr{IP: net.ParseIP("127.0.0.1"), Port: rtpPort})
	if err != nil {
		panic(err)
	}

	// Listen for a single RTP Packet, we need this to determine the SSRC
	inboundRTPPacket := make([]byte, 4096) // UDP MTU
	n, _, err := listener.ReadFromUDP(inboundRTPPacket)
	if err != nil {
		panic(err)
	}

	// Unmarshal the incoming packet
	packet := &rtp.Packet{}
	if err = packet.Unmarshal(inboundRTPPacket[:n]); err != nil {
		panic(err)
	}

	return listener, packet.SSRC
}

func (c *ccImpl) VideoStream() chan rtp.Packet {
	return c.videoStream
}

// Listen to videostream, output to videoStream channel
func (c *ccImpl) listenVideoStream() {
	// Broadcast video stream
	go func() {
		defer func() {
			c.listener.Close()
			log.Println("Closing game VM")
			// close(gameVMDone)
		}()

		// Read RTP packets forever and send them to the WebRTC Client
		for {
			inboundRTPPacket := make([]byte, 4096) // UDP MTU
			n, _, err := c.listener.ReadFrom(inboundRTPPacket)
			if err != nil {
				log.Printf("error during read: %s", err)
				continue
			}

			packet := rtp.Packet{}
			if err := packet.Unmarshal(inboundRTPPacket[:n]); err != nil {
				log.Printf("error during unmarshalling a packet: %s", err)
				continue
			}
			packet.Header.PayloadType = webrtc.DefaultPayloadTypeVP8

			c.videoStream <- packet
		}
	}()

}

func (c *ccImpl) SendInput(packet WSPacket) {
	switch packet.PType {
	case eventKeyDown:
		c.simulateKeyDown(packet.Data)
	case eventMouse:
		c.simulateMouseEvent(packet.Data)
	}
}

func (c *ccImpl) simulateKeyDown(jsonPayload string) {
	if !c.isReady {
		return
	}
	// if isStarted == false {
	// 	return
	// }
	// if WineConn == nil {
	// 	return
	// }

	log.Println("KeyDown event", jsonPayload)
	type keydownPayload struct {
		KeyCode int `json:keycode`
	}
	p := &keydownPayload{}
	json.Unmarshal([]byte(jsonPayload), &p)

	b, err := c.wineConn.Write([]byte{byte(p.KeyCode)})
	log.Printf("%+v\n", c.wineConn)
	log.Println("Sended key: ", b, err)
}

// simulateMouseEvent handles mouse down event and send it to Virtual Machine over TCP port
func (c *ccImpl) simulateMouseEvent(jsonPayload string) {
	// if isStarted == false {
	// 	return
	// }
	// if WineConn == nil {
	// 	return
	// }
	if !c.isReady {
		return
	}

	log.Println("MouseDown event", jsonPayload)
	type mousedownPayload struct {
		IsLeft byte    `json:isLeft`
		IsDown byte    `json:isDown`
		X      float32 `json:x`
		Y      float32 `json:y`
		Width  float32 `json:width`
		Height float32 `json:height`
	}
	p := &mousedownPayload{}
	json.Unmarshal([]byte(jsonPayload), &p)

	// Mouse is in format of comma separated "12.4,52.3"
	mousePayload := fmt.Sprintf("%d,%d,%f,%f,%f,%f", p.IsLeft, p.IsDown, p.X, p.Y, p.Width, p.Height)
	b, err := c.wineConn.Write([]byte(mousePayload))
	// log.Printf("%+v\n", WineConn)
	log.Println("Sended Mouse: ", b, err)
}
