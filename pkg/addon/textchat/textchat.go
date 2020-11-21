package textchat

import (
	"encoding/json"
	"fmt"
	"log"

	"github.com/giongto35/cloud-morph/pkg/common/cws"
)

type ChatMessage struct {
	User    string `json:"user"`
	Message string `json:"message"`
}

type TextChat struct {
	chatMsgs    []ChatMessage
	broadcastCh chan ChatMessage
	clients     map[string]*chatClient
}

type chatClient struct {
	clientID    string
	ws          *cws.Client
	broadcastCh chan ChatMessage
	WSEvents    chan cws.Packet
}

func NewTextChat() *TextChat {
	return &TextChat{
		chatMsgs:    []ChatMessage{},
		clients:     map[string]*chatClient{},
		broadcastCh: make(chan ChatMessage, 1),
	}
}

func Convert(packet cws.Packet) ChatMessage {
	chatMsg := ChatMessage{}
	err := json.Unmarshal([]byte(packet.Data), &chatMsg)
	if err != nil {
		panic(err)
	}

	return chatMsg
}

func (t *TextChat) broadcast(e ChatMessage) error {
	data, err := json.Marshal(ChatMessage{
		User:    e.User,
		Message: e.Message,
	})
	if err != nil {
		return err
	}
	for _, client := range t.clients {
		client.Send(cws.Packet{
			PType: "CHAT",
			Data:  string(data),
		})
	}
	t.chatMsgs = append(t.chatMsgs, e)

	return nil
}

func (t *TextChat) Handle() {
	for e := range t.broadcastCh {
		t.broadcast(e)
	}
}

func NewChatClient(clientID string, ws *cws.Client, broadcastCh chan ChatMessage, wsEvents chan cws.Packet) *chatClient {
	return &chatClient{
		broadcastCh: broadcastCh,
		clientID:    clientID,
		ws:          ws,
		WSEvents:    wsEvents,
	}
}

func (c *chatClient) Listen() {
	// defer func() {
	// 	close(c.done)
	// }()

	log.Println("Client listening")
	for wspacket := range c.WSEvents {
		c.broadcastCh <- Convert(wspacket)
	}
}

func (t *TextChat) AddClient(clientID string, ws *cws.Client) *chatClient {
	client := NewChatClient(clientID, ws, t.broadcastCh, make(chan cws.Packet, 1))
	go client.Listen()
	t.clients[clientID] = client
	return client
}

func (t *TextChat) SendChatHistory(clientID string) {
	client, ok := t.clients[clientID]
	if !ok {
		fmt.Println("Client not found", clientID)
		return
	}

	for _, msg := range t.chatMsgs {
		data, err := json.Marshal(ChatMessage{
			User:    msg.User,
			Message: msg.Message,
		})
		if err != nil {
			log.Println("Failed to send ", msg)
			continue
		}

		client.Send(cws.Packet{
			PType: "CHAT",
			Data:  string(data),
		})
	}
}

// func (c *chatClient) Send(packet cws.Packet) error {
// 	data, err := json.Marshal(packet)
// 	if err != nil {
// 		return err
// 	}

// 	c.ws.WriteMessage(websocket.TextMessage, data)
// 	return nil
// }

func (c *chatClient) Close() {
}
