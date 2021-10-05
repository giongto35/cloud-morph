package main

import (
	"context"
	"flag"
	"log"
	"runtime"
	"syscall"

	"github.com/giongto35/cloud-morph/pkg/shim"
)

type app struct {
	hWnd      syscall.Handle
	isDirectX bool
}

var App app

func main() {
	oss := runtime.GOOS
	addr := flag.String("addr", ":9090", "Server address")
	title := flag.String("title", "Minesweeper", "Application title")
	dxApp := flag.Bool("dx", false, "If running a DirectX application")

	flag.Parse()

	log.Printf("OS: %v", oss)
	log.Printf("Settings: addr=[%v], title=[%v], dx=[%v]", *addr, *title, *dxApp)

	hWnd, err := shim.FindWindow(*title)
	if err != nil {
		log.Fatalf("error: %v window fail. %v", *title, err)
	}
	App.hWnd = hWnd
	App.isDirectX = *dxApp

	err = shim.Client{}.
		Connect(context.Background(), *addr, onAppMessages(&App))
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
