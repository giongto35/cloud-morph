package textchat

import (
	"encoding/json"
	"fmt"
	"log"

	"github.com/giongto35/cloud-morph/pkg/common/ws"
)

type ChatMessage struct {
	User    string `json:"user"`
	Message string `json:"message"`
}

type TextChat struct {
	chatMsgs []ChatMessage
	events   chan ChatMessage
	clients  map[string]*ws.Client
}

func NewTextChat(events chan ChatMessage) *TextChat {
	return &TextChat{
		chatMsgs: []ChatMessage{},
		clients:  map[string]*ws.Client{},
		events:   events,
	}
}

func Convert(packet ws.Packet) ChatMessage {
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
		client.Send(ws.Packet{
			PType: "CHAT",
			Data:  string(data),
		})
	}

	return nil
}

func (t *TextChat) Handle() {
	for e := range t.events {
		t.broadcast(e)
	}
}

func (t *TextChat) AddClient(clientID string, client *ws.Client) {
	t.clients[clientID] = client
}

func (t *TextChat) SendChatHistory(clientID string, chatMsgs []ChatMessage) {
	client, ok := t.clients[clientID]
	if !ok {
		return
	}

	for _, msg := range chatMsgs {
		data, err := json.Marshal(ChatMessage{
			User:    msg.User,
			Message: msg.Message,
		})
		if err != nil {
			log.Println("Failed to send ", msg)
			continue
		}
		fmt.Println("chat history ", data)

		client.Send(ws.Packet{
			PType: "CHAT",
			Data:  string(data),
		})
	}
}
