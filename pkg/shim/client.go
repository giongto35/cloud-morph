//go:build windows
// +build windows

package shim

import (
	"bufio"
	"context"
	"fmt"
	"log"
	"net"
	"time"
)

const (
	PingTimeout = 6 * time.Second
	ReadDelim   = '|'
)

type Client struct{}

func (c Client) Connect(ctx context.Context, addr string, onMessage func(_ string)) (err error) {
	conn, err := net.DialTimeout("tcp", addr, PingTimeout)
	if err != nil {
		return err
	}
	defer func() {
		_ = conn.Close()
		log.Printf("Disconnected")
	}()
	log.Printf("Connected to %v", conn.LocalAddr().String())

	ping := time.NewTicker(PingTimeout * 9 / 10)
	defer ping.Stop()
	ts := time.Now()

	reader := bufio.NewReader(conn)
	ctx, cancel := context.WithCancel(ctx)
	defer cancel()

	// serial polling
	for {
		select {
		default:
			// ping -> [0], message -> ![0]
			if b, err := reader.ReadByte(); err == nil {
				if b == 0 {
					ts = time.Now()
					break
				}
				_ = reader.UnreadByte()
				if mess, err := reader.ReadString(ReadDelim); err == nil {
					// message 123| -> message 123
					go onMessage(mess[:len(mess)-1])
				}
			}
		case <-ping.C:
			if time.Now().Sub(ts) > PingTimeout {
				cancel()
				return fmt.Errorf("connection timeout has been exceeded (%v)", PingTimeout)
			}
		case <-ctx.Done():
			return
		}
	}
}
