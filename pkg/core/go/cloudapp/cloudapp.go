// Package cloudapp is an individual cloud application
package cloudapp

import (
	"bufio"
	"container/ring"
	"encoding/json"
	"fmt"
	"log"
	"net"
	"os"
	"os/exec"
	"runtime"
	"strconv"
	"time"

	"github.com/giongto35/cloud-morph/pkg/common/config"
	"github.com/giongto35/cloud-morph/pkg/common/cws"
	"github.com/pion/rtp"
)

type CloudAppClient interface {
	VideoStream() chan *rtp.Packet
	AudioStream() chan *rtp.Packet
	SendInput(Packet)
	Handle()
}

type osTypeEnum int

const (
	Linux osTypeEnum = iota
	Mac
	Windows
)

type ccImpl struct {
	isReady       bool
	videoListener *net.UDPConn
	audioListener *net.UDPConn
	videoStream   chan *rtp.Packet
	audioStream   chan *rtp.Packet
	appEvents     chan Packet
	wineConn      *net.TCPConn
	osType        osTypeEnum
	screenWidth   float32
	screenHeight  float32
	ssrc          uint32
}

// Packet represents a packet in cloudapp
type Packet struct {
	Type string `json:"type"`
	Data string `json:"data"`
}

const startVideoRTPPort = 5004
const startAudioRTPPort = 4004
const eventKeyDown = "KEYDOWN"
const eventKeyUp = "KEYUP"
const eventMouseMove = "MOUSEMOVE"
const eventMouseDown = "MOUSEDOWN"
const eventMouseUp = "MOUSEUP"

var curVideoRTPPort = startVideoRTPPort
var curAudioRTPPort = startAudioRTPPort

// NewCloudAppClient returns new cloudapp client
func NewCloudAppClient(cfg config.Config, appEvents chan Packet) *ccImpl {
	c := &ccImpl{
		videoStream: make(chan *rtp.Packet, 1),
		audioStream: make(chan *rtp.Packet, 1),
		appEvents:   appEvents,
	}

	switch runtime.GOOS {
	case "windows":
		c.osType = Windows
	default:
		c.osType = Linux
	}

	la, err := net.ResolveTCPAddr("tcp4", ":9090")
	if err != nil {
		panic(err)
	}
	log.Println("listening syncinput at port 9090")
	ln, err := net.ListenTCP("tcp", la)
	if err != nil {
		panic(err)
	}

	fmt.Println(cfg)
	c.launchAppVM(curVideoRTPPort, curAudioRTPPort, cfg)
	log.Println("Launched application VM")

	// Read video stream from encoded video stream produced by FFMPEG
	log.Println("Setup Video Listener")
	videoListener, listenerssrc := c.newLocalStreamListener(curVideoRTPPort)
	c.videoListener = videoListener
	c.ssrc = listenerssrc
	if c.osType != Windows {
		// Don't spawn Audio in Windows
		log.Println("Setup Audio Listener")
		audioListener, audiolistenerssrc := c.newLocalStreamListener(curAudioRTPPort)
		c.audioListener = audioListener
		c.ssrc = audiolistenerssrc
	}
	log.Println("Done Listener")

	c.listenVideoStream()
	log.Println("Launched Video stream listener")
	if c.osType != Windows {
		// Don't spawn Audio in Windows
		c.listenAudioStream()
		log.Println("Launched Audio stream listener")
	}

	// Maintain input stream from server to Virtual Machine over websocket
	go c.healthCheckVM()
	// NOTE: Why Websocket: because normal IPC cannot communicate cross OS.
	go func() {
		for {
			log.Println("Waiting syncinput to connect")
			// Polling Wine socket connection (input stream)
			conn, err := ln.AcceptTCP()
			log.Println("Accepted a TCP connection")
			if err != nil {
				log.Println("err: ", err)
			}
			conn.SetKeepAlive(true)
			conn.SetKeepAlivePeriod(10 * time.Second)
			c.wineConn = conn
			c.isReady = true
			log.Println("Launched IPC with VM")
		}
	}()

	return c
}

// convertWSPacket returns cloudapp packet from ws packet
func convertWSPacket(packet cws.WSPacket) Packet {
	return Packet{
		Type: packet.Type,
		Data: packet.Data,
	}
}

func (c *ccImpl) GetSSRC() uint32 {
	return c.ssrc
}

func (c *ccImpl) runApp(execCmd string, params []string) chan struct{} {
	log.Println("params: ", params)

	var cmd *exec.Cmd
	cmd = exec.Command(execCmd, params...)

	cmd.Env = os.Environ()
	stdout, err := cmd.StdoutPipe()
	if err != nil {
		log.Fatal(err)
	}
	go func() {
		scanner := bufio.NewScanner(stdout)
		for scanner.Scan() {
			log.Printf(scanner.Text())
		}
	}()
	stderr, err := cmd.StderrPipe()
	if err != nil {
		log.Fatal(err)
	}
	go func() {
		scanner := bufio.NewScanner(stderr)
		for scanner.Scan() {
			log.Printf(scanner.Text())
		}
	}()
	err = cmd.Start()
	if err != nil {
		log.Printf("err: cmd fail, %v", err)
		return nil
	}
	log.Println("Done running script")
	err = cmd.Wait()
	if err != nil {
		log.Printf("err: cmd fail, %v", err)
		return nil
	}

	done := make(chan struct{})
	// clean up func
	go func() {
		<-done
		err := cmd.Process.Kill()
		cmd.Process.Kill()
		log.Println("Kill app: ", err)
	}()
	return done
}

// done to forcefully stop all processes
func (c *ccImpl) launchAppVM(curVideoRTPPort int, curAudioRTPPort int, cfg config.Config) chan struct{} {
	var execCmd string
	var params []string

	// Setup wine params and run
	log.Println("execing run-wine.sh")
	// TODO: refactor to key value
	// Add Exec command based on platform
	if c.osType == Windows {
		log.Println("You are running on Windows")
		execCmd = "powershell"
		params = append(params, []string{"-ExecutionPolicy", "Bypass", "-F"}...)
		if cfg.IsVirtualized {
			params = append(params, "run-sandbox.ps1")
		} else {
			params = append(params, "run-app.ps1")
		}
	} else {
		log.Println("You are running on Linux")
		execCmd = "./run-wine.sh"
	}
	// Add params
	if c.osType == Windows {
		params = append(params, cfg.Path)
	} else {
		params = append(params, "/"+cfg.Path) // Path in docker container after mount is at root
	}
	params = append(params, []string{cfg.AppFile, cfg.WindowTitle}...)
	if cfg.HWKey {
		params = append(params, "game")
	} else {
		params = append(params, "app")
	}
	params = append(params, []string{strconv.Itoa(cfg.ScreenWidth), strconv.Itoa(cfg.ScreenHeight)}...)
	if *cfg.IsWindowMode {
		params = append(params, "-w")
	} else {
		params = append(params, "")
	}
	if c.osType == Windows {
		params = append(params, "windows")
		params = append(params, "-vcodec", cfg.VideoCodec)
	} else {
		params = append(params, "")
	}
	c.screenWidth = float32(cfg.ScreenWidth)
	c.screenHeight = float32(cfg.ScreenHeight)

	return c.runApp(execCmd, params)
}

// healthCheckVM to maintain connection with Virtual Machine
func (c *ccImpl) healthCheckVM() {
	log.Println("Starting health check")
	for {
		if c.wineConn != nil {
			_, err := c.wineConn.Write([]byte{0})
			if err != nil {
				log.Println(err)
			}
		}
		time.Sleep(2 * time.Second)
	}
}

func (c *ccImpl) Handle() {
	for event := range c.appEvents {
		c.SendInput(event)
	}
}

// newLocalStreamListener returns RTP: listener and SSRC of that listener
func (c *ccImpl) newLocalStreamListener(rtpPort int) (*net.UDPConn, uint32) {
	// Open a UDP Listener for RTP Packets on port 5004
	listener, err := net.ListenUDP("udp", &net.UDPAddr{IP: net.ParseIP("localhost"), Port: rtpPort})
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

func (c *ccImpl) VideoStream() chan *rtp.Packet {
	return c.videoStream
}

func (c *ccImpl) AudioStream() chan *rtp.Packet {
	return c.audioStream
}

// Listen to videostream, output to videoStream channel
func (c *ccImpl) listenAudioStream() {

	// Broadcast video stream
	go func() {
		defer func() {
			c.audioListener.Close()
			log.Println("Closing app VM")
		}()
		r := ring.New(120)

		n := r.Len()
		for i := 0; i < n; i++ {
			// r.Value = make([]byte, 4096)
			r.Value = make([]byte, 1500)
			r = r.Next()
		}

		// TODO: Create a precreated memory, only pop after finish processing
		// Read RTP packets forever and send them to the WebRTC Client
		for {
			inboundRTPPacket := r.Value.([]byte) // UDP MTU
			r = r.Next()
			n, _, err := c.audioListener.ReadFrom(inboundRTPPacket)
			if err != nil {
				log.Printf("error during read: %s", err)
				continue
			}

			// TODOs: Don't assign packet here
			packet := &rtp.Packet{}
			if err := packet.Unmarshal(inboundRTPPacket[:n]); err != nil {
				log.Printf("error during unmarshalling a packet: %s", err)
				continue
			}

			c.audioStream <- packet
		}
	}()

}

// Listen to videostream, output to videoStream channel
func (c *ccImpl) listenVideoStream() {

	// Broadcast video stream
	go func() {
		defer func() {
			c.videoListener.Close()
			log.Println("Closing app VM")
		}()
		r := ring.New(120)

		n := r.Len()
		for i := 0; i < n; i++ {
			// r.Value = make([]byte, 4096)
			r.Value = make([]byte, 1500)
			r = r.Next()
		}

		// TODO: Create a precreated memory, only pop after finish processing
		// Read RTP packets forever and send them to the WebRTC Client
		for {
			inboundRTPPacket := r.Value.([]byte) // UDP MTU
			r = r.Next()
			n, _, err := c.videoListener.ReadFrom(inboundRTPPacket)
			if err != nil {
				log.Printf("error during read: %s", err)
				continue
			}

			// TODOs: Don't assign packet here
			packet := &rtp.Packet{}
			if err := packet.Unmarshal(inboundRTPPacket[:n]); err != nil {
				log.Printf("error during unmarshalling a packet: %s", err)
				continue
			}

			c.videoStream <- packet
		}
	}()

}

func (c *ccImpl) SendInput(packet Packet) {
	switch packet.Type {
	case eventKeyUp:
		c.simulateKey(packet.Data, 0)
	case eventKeyDown:
		c.simulateKey(packet.Data, 1)
	case eventMouseMove:
		c.simulateMouseEvent(packet.Data, 0)
	case eventMouseDown:
		c.simulateMouseEvent(packet.Data, 1)
	case eventMouseUp:
		c.simulateMouseEvent(packet.Data, 2)
	}
}

func (c *ccImpl) simulateKey(jsonPayload string, keyState byte) {
	if !c.isReady {
		return
	}

	log.Println("KeyDown event", jsonPayload)
	type keydownPayload struct {
		KeyCode int `json:keycode`
	}
	p := &keydownPayload{}
	json.Unmarshal([]byte(jsonPayload), &p)

	vmKeyMsg := fmt.Sprintf("K%d,%b|", p.KeyCode, keyState)
	b, err := c.wineConn.Write([]byte(vmKeyMsg))
	log.Printf("%+v\n", c.wineConn)
	log.Println("Sended key: ", b, err)
}

// simulateMouseEvent handles mouse down event and send it to Virtual Machine over TCP port
func (c *ccImpl) simulateMouseEvent(jsonPayload string, mouseState int) {
	if !c.isReady {
		return
	}

	type mousePayload struct {
		IsLeft byte    `json:isLeft`
		X      float32 `json:x`
		Y      float32 `json:y`
		Width  float32 `json:width`
		Height float32 `json:height`
	}
	p := &mousePayload{}
	json.Unmarshal([]byte(jsonPayload), &p)
	p.X = p.X * c.screenWidth / p.Width
	p.Y = p.Y * c.screenHeight / p.Height

	// Mouse is in format of comma separated "12.4,52.3"
	vmMouseMsg := fmt.Sprintf("M%d,%d,%f,%f,%f,%f|", p.IsLeft, mouseState, p.X, p.Y, p.Width, p.Height)
	_, err := c.wineConn.Write([]byte(vmMouseMsg))
	if err != nil {
		fmt.Println("Err: ", err)
	}
}
