package mesh

import (
	"github.com/giongto35/cloud-morph/pkg/common/ws"
)

type DiscoveryClient struct {
	WSEvents chan ws.Packet
}

func (c *DiscoveryClient) WebsocketListen() {
	// Listen from video stream
	for wspacket := range c.WSEvents {
		if wspacket.PType == "SELECTHOST" {
		}
	}
}
