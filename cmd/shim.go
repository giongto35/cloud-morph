package main

import (
	"context"
	"flag"
	"log"
	"net"
	"runtime"
	"syscall"
	"time"

	"github.com/giongto35/cloud-morph/pkg/shim"
)

type app struct {
	hWnd      syscall.Handle
	isDirectX bool
	title     string
}

func main() {
	oss := runtime.GOOS
	addr := *flag.String("addr", ":9090", "Server address")
	title := *flag.String("title", "Minesweeper", "Application title")
	dxApp := *flag.Bool("dx", false, "If running a DirectX application")

	flag.Parse()

	log.Printf("OS: %v", oss)

	// macOS == docker, why?
	if oss == "darwin" {
		_, port, err := net.SplitHostPort(addr)
		if err == nil {
			addr = net.JoinHostPort("host.docker.internal", port)
		}
	}
	log.Printf("Settings: addr=[%v], title=[%v], dx=[%v]", addr, title, dxApp)

	hWnd, _ := findWindow(title)
	// ???
	shim.FormatWindow(hWnd)
	app := app{
		hWnd:      hWnd,
		isDirectX: dxApp,
		title:     title,
	}
	go trackWindow(&app)

	err := shim.Client{}.Connect(context.Background(), addr, onAppMessages(&app))
	if err != nil {
		log.Printf("error: %v", err)
	}
	_ = shim.FreeLibs()
}

func onAppMessages(app *app) func(message string) {
	return func(message string) {
		switch message[0] {
		case 'K':
			if key, event, err := shim.FromKey(message); err == nil {
				log.Printf("Got: %v, %v", key, event)
				shim.SendKeyEvent(uintptr(app.hWnd), key, event, app.isDirectX)
			}
		case 'M':
			if mouse, event, err := shim.FromMouse(message); err == nil {
				log.Printf("Got: %v, %v", mouse, event)
				shim.SendMouseEvent(mouse, event)
			}
		default:
			log.Printf("?, %v", message)
		}
	}
}

func findWindow(title string) (syscall.Handle, error) {
	hWnd, err := shim.FindWindow(title)
	if err != nil {
		log.Fatalf("error: %v window fail. %v", title, err)
	}
	return hWnd, err
}

func trackWindow(app *app) {
	log.Printf("Window tracking has been started")
	track := time.NewTicker(5 * time.Second)
	defer track.Stop()
	for {
		select {
		case <-track.C:
			hWnd, _ := findWindow(app.title)
			if hWnd != app.hWnd {
				// ???
				shim.FormatWindow(hWnd)
				app.hWnd = hWnd
				log.Printf("Window handler changed")
			}
		}
	}
}
