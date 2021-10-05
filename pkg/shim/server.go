package shim

import (
	"context"
	"log"
	"net"
	"time"
)

const keepAliveTimeout = 10 * time.Second

type Server struct {
	conn    *net.TCPConn
	isReady bool
}

func (s *Server) Start(ctx context.Context) {
	la, err := net.ResolveTCPAddr("tcp4", ":9090")
	if err != nil {
		panic(err)
	}
	log.Println("listening wine at port 9090")
	ln, err := net.ListenTCP("tcp", la)
	if err != nil {
		panic(err)
	}

	ctx, cancel := context.WithCancel(ctx)
	defer cancel()

	var conns = make(chan net.Conn)

	go func() {
		for {
			conn, err := ln.AcceptTCP()
			if err != nil {
				log.Printf("Accept failed: %v", err)
				continue
			}
			_ = conn.SetKeepAlive(true)
			_ = conn.SetKeepAlivePeriod(keepAliveTimeout)
			conns <- conn
		}
	}()

	// manual ping
	ping := time.NewTicker(keepAliveTimeout / 2)
	ping.Stop()
	defer ping.Stop()
	for {
		select {
		case conn := <-conns:
			s.conn = conn.(*net.TCPConn)
			s.isReady = true
			ping.Reset(keepAliveTimeout / 2)
			log.Printf("New connection from %v", s.conn.RemoteAddr())
		case <-ping.C:
			_, err := s.Write(PING)
			if err != nil {
				s.isReady = false
				if s.conn != nil {
					_ = s.conn.Close()
					log.Printf("Close")
				}
				ping.Stop()
				log.Printf("Disconnect from %v", s.conn.RemoteAddr())
			}
		case <-ctx.Done():
			s.isReady = false
			if s.conn != nil {
				_ = s.conn.Close()
			}
			log.Printf("Shutdown")
			return
		}
	}
}

func (s *Server) IsReady() bool { return s.isReady }

func (s *Server) Write(data []byte) (int, error) { return s.conn.Write(data) }
