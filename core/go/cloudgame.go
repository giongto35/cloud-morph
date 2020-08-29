package cloudgame

import (
	"encoding/json"
	"fmt"
	"log"

	"github.com/pion/rtp"
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

type CloudgameClient interface {
	videoStream() chan *rtp.Packet
	sendInput(InputEvent)
}

func (c *CloudgameClient) simulateKeyDown(jsonPayload string) {
	if isStarted == false {
		return
	}
	if WineConn == nil {
		return
	}

	log.Println("KeyDown event", jsonPayload)
	type keydownPayload struct {
		KeyCode int `json:keycode`
	}
	p := &keydownPayload{}
	json.Unmarshal([]byte(jsonPayload), &p)

	b, err := WineConn.Write([]byte{byte(p.KeyCode)})
	log.Printf("%+v\n", WineConn)
	log.Println("Sended key: ", b, err)
}

// simulateMouseEvent handles mouse down event and send it to Virtual Machine over TCP port
func simulateMouseEvent(jsonPayload string) {
	if isStarted == false {
		return
	}
	if WineConn == nil {
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
	b, err := WineConn.Write([]byte(mousePayload))
	log.Printf("%+v\n", WineConn)
	log.Println("Sended Mouse: ", b, err)
}
