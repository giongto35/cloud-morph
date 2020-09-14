package textchat

import (
	"encoding/json"
	"fmt"
	"log"

	"github.com/giongto35/cloud-morph/pkg/common"
	"github.com/giongto35/cloud-morph/pkg/core/go/cloudgame"
)

type TextClient interface {
	Send(packet cloudgame.WSPacket)
}

type TextServer interface {
}

type ChatMessage struct {
	User    string `json:"user"`
	Message string `json:"message"`
}

type TextChat struct {
	chatMsgs  []ChatMessage
	textEvent chan ChatMessage
	clients   map[string]TextClient
	server    TextServer
}

func NewTextChat(client TextClient, server TextServer) *TextChat {
	return &TextChat{
		chatMsgs: []ChatMessage{},
		clients:  map[string]TextClient{},
		server:   server,
	}
}

func Convert(packet common.WSPacket) ChatMessage {
	chatMsg := ChatMessage{}
	err := json.Unmarshal([]byte(packet.Data), &chatMsg)
	if err != nil {
		panic(err)
	}

	return chatMsg
}

func (t *TextChat) sendChatHistory(clientID string, chatMsgs []ChatMessage) {
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

		client.Send(cloudgame.WSPacket{
			PType: "CHAT",
			Data:  string(data),
		})
	}
}
