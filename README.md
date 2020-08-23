# CloudMorph
(IN DEVELOPMENT)

**Bring offline app to cloud, Run directly on browser

## Introduction
|                   Screenshot                   |                   Screenshot                   |
| :--------------------------------------------: | :--------------------------------------------: |
| ![screenshot](docs/img/landing-page-ps-hm.png) | ![screenshot](docs/img/landing-page-ps-x4.png) |
| ![screenshot](docs/img/landing-page-gb.png)    | ![screenshot](docs/img/landing-page-front.png) |

## Build
Install Golang
- go run server.go
Open: localhost:8080

## Design 
(TOBE updated)

## Challenge
### Why picking wine
- First, I consider writing the whole system in Window. However, Window lacks programming utilities and I am more familiar with 
### Headless server
- Being able to run on Headless server is a goal. If we attach the server to an existing machine 's DISPLAY, we cannot improvision
### Running window app in headless mode
- The first thing I tried is running wine directly on a headless server.
### Why XVFB, not X11VNC (Remote access)

### Why Golang
