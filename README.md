
**Decentralized, Self-hosted cloud gaming/cloud application service.**

## Introduction

CloudMorph is a decentralized, self-hosted cloud gaming/cloud application platform. User can host their cloud gaming solution with minimum configuration. By leveraging the ease of deployment, CloudMorph goal is to build a decentralized cloud-gaming network with providers and consumers. 
To bring a scalable, performant and universal cloud gaming solution, CloudMorph has to cope with many technical challenges from Windows application Virtualization in headless server, OS event simulation, Video/Audio encoding pipeline and optimization, NAT traversal, P2P network structurization, etc.

## Demo

Video Demo: https://www.youtube.com/watch?v=fkOpOQ-HwFY

|                       Screenshot                       |                        Screenshot                         |
| :----------------------------------------------------: | :-------------------------------------------------------: |
| ![screenshot](docs/img/screenshotDiablo.png) Diablo II | ![screenshot](docs/img/screenshotPhotoshop.png) Photoshop |
| ![screenshot](docs/img/screenshotRoadrash.png) [RoadRash](https://www.youtube.com/watch?v=A2JcFaVlOO4) | ![screenshot](docs/img/screenshotStarcraft.png) Starcraft  |

#### Demo Hosted by CloudMorph
- [Cloud Diablo SG](http://clouddiablo.com/) (Demo of Collaborative play Diablo running on Singapore server using CloudMorph)
- [Cloud Diablo US](http://us.clouddiablo.com/) (Demo of Collaborative play Diablo running in US server).
Switch Applications using the sidebar on the left.

#### Experience deployment on your own:
- Run `setup_remote.sh 111.111.111.111` with 111.111.111.111 is your host. What you will get is a Notepad hosted on your remote machine. More details about deployment is below

## Design Goal:
1. **Simplicity**: No API/ interface integration needed from application. One line script deployment to a public server to get work done.
2. **Mesh network**: Providers-Consumers over Peer To Peer communication. After joining the network, Provider's Application is discoverable and launched with one click.
3. **Modularizable**: A concise technical stack to **develop**/**deploy** for cloud gaming/ cloud application service.
4. **Generic/Cross-platform**: Run on web browser, web mobile. Target Windows App instead of relying on gaming framework/emulator. (like [CloudRetro](https://github.com/giongto35/cloud-game)).
5. **Scalable**: Be able to scale on headless machines cluster horizontally.

## Deployment

Foremost, you need an Ubuntu instance with a public network firewall. For example, you can use the given `script/create_do.sh` to create a digital ocean instance.
Then we need 3 in the same folder:
1. `config.yaml`: app config, the app configuration
3. `wine`: whole wine folder from `.wine`. If there is no wine folder, the basic wine envirnoment will be you.
5. `apps`: a folder contains the app you want to deploy. For example, `DiabloII`. If your application is from other folder ex "Program Files", we can leave it empty. We just need to configure the `config.yaml`
6. `setup_remote.sh`: a script to deploy your application to server

Example:
- `setup_remote.sh $ip $mount_path`. Ex: `./setup_remote.sh 159.89.146.77 /apps/DiabloII`  
- Tutorial Video: https://www.youtube.com/watch?v=w8uCkfZdHVc

### Deployment with Lutris
- Lutris eases the installation of a game on Linux. **The recommended flow is to install game with Lutris and copy produced wine environment to Cloud Morph**

### Deployment Example
- `script/example` contains example applications configuration. Note: `/apps` is left empty due to copyright.

# Technical
## Development

The service is based on Golang, C++, and Linux X11 utility tools (Xvfb, ffmpeg).
You can set up all dependencies with `setup.sh`. After that, you can run the go server with

- `go run server.go`

Access to your local at

- `localhost:8080`

Note: the wine application is run in Docker. You can run it without docker by changing `run-wine.sh` to `run-wine-nodocker.sh` in `server.go` for easier debugging.

## Real-World Usecase
Unlike **[CloudRetro](https://github.com/giongto35/cloud-game)**, a Completed Cloud Gaming solution on Retro Game hosted on dedicated cloud infrastructure, CloudMorph generalizes the system to bring any offline Windows application to a cloud mesh network. The deployment is simplified with a concise tech-stack and codebase. The goal is to create a distributed cloud application system when anyone can contribute their offline application on the platform, and other people can consume it.

##### For Developers
- Experience playing/hosting Cloud Gaming on their own.
- Plugable Cloud gaming module: The cloud gaming core is packaged and virtualized to be easily extended to different tech stacks.

##### For Consumers.
- Multi-platform: be able to run web-browser, mobile web.
- Collaborative Gaming: Multiple people plays the same game. Ex. Twitch play pokemon, or http://clouddiablo.com/ - A cloudmorph demo.

##### For Providers
- Playable Teaser: Application's teaser is playable, 

## Design

- **Mesh Network**
![screenshot](docs/img/Decentralize.png)

- **CloudApp core**
![screenshot](docs/img/CloudUniverse.png)

- When Webserver starts, Wine Application is spawned inside a container at the same time. However, in the future, Wine Application needs to support multiplex to run multiple applications in the same VM.
- Input captured from Client is sent to Virtual Machine over Websocket.
- A C++ script (syncinput.exe) will listen to the event and simulates Windows OS event to Wine Application through WinAPI.
- Application screen is captured in a Virtual Display Frame Buffer, which is later piped to FFMPEG.
- FFMPEG will produce the screen stream to a VPX RTP stream.

- In the end, the core module receives **Input** as WebSocket event and **Output** as RTP stream. You can check the interface at `core/go/cloudapp`
- Webserver interacts with Virtual Machine using these Input and Output format.

## Technical

#### WebRTC
- WebRTC is crucial technology for P2P communication. It helps:
  - Direct Communication between Provider and consumer.
  - NAT Traversal by ICE.
    - Find a best way for direct P2P communication
- RTP: Real Time Transport Protocol
  - UDP underline
- With [Pion](https://github.com/pion/webrtc/) library in Go, WebRTC streaming becomes really handy.

#### Windows Virtualization on Linux OS

- Windows is an essential OS for gaming application. Linux is development friendly and provides more programming utilities.
- First, I consider writing the whole system in Windows. However, Windows lacks programming utilities, and Linux is more comfortable for me.
- Wine is a Windows Virtual Machine. Its performance is proven in Steam PlayOnLinux. Lutris.

#### Headless server

- Headless server is a server without display. When you acquire any cloud instances from AWS, Digital Ocean, GCloud..., it is headless because there is no monitor attached to it.
- One of the most challenging problems is to deal with Headless when your application/game always requires a graphic monitor, graphic driver. Being able to run on a Headless server is a goal. We can improvision new application instances and scale gaming sessions properly.

#### Inter Process Communication between Web Service and Cloud Gaming Container

- Even though Wine application and server stay in the same machine, they theoretically run on different OS. Normal Internal Process Communication becomes challenging and not suitable. Network communication using Websocket over some defined ports can help in this case.

#### Video/Audio Encoding pipeline

- FFMPEG is used to grab XVFB Display (built-in functionality) and convert it to the VPX video stream. It can be substituted with GStreamer or any custom encoding solution.

#### Event Simulation
- C++ is chosen because it has good support for WindowsAPI.

## Road Map - Request for Help

- UI improvement
- Full Dockerization. Currently server is not run in Container.
- Port C++ Window API to Rust.
- GPU acceleration. - Integrate with FFMPEG job. 
- Multiplex application sessions. Currently, only collaborative mode is supported, which serves all application's sessions from the same single instance.
- Performance optimization.
- Web Mobile controller supprt. Currently, mouse click is already simulated.
- Packaging frontend as a plugin that can be imported in any Webpage.
