# Jetson and service setup

## Jetson terminal

`razaai-8g` targets the Jetson Orin Nano Developer Kit with 8 GB shared memory. Install JetPack and Ollama first, then run:

```bash
./deploy.sh 8g
sudo deploy/jetson-headless.sh
./razaai-8g
```

The Jetson version runs in the terminal. It has no browser or HTTP server. Use the terminal on the device or connect over SSH:

```bash
ssh your-user@jetson-address
razaai-8g
# For a coding project:
razaai-8g code ~/Projects/my-project
```

Use `tmux` if you want the terminal session to survive a disconnected SSH connection. When JetPack's USB device networking is enabled, the Jetson commonly uses `192.168.55.1`. Confirm the address with `ip address`; USB configuration varies by image.

## Ollama memory settings

`deploy/jetson-headless.sh` installs a dedicated Ollama service override and restarts Ollama. It enables flash attention, a quantized KV cache, one parallel request, and one resident model. RazaAI sends a 4,096-token context limit and a 128-token prompt batch in each inference request.

The 8 GB profile checks model metadata before loading. Models must have at most 4.5 billion parameters and use 4-bit quantization. Context, desktop use and other processes still affect available memory. These limits are not a measured guarantee of fit. Check `ollama ps`, `free -h`, and `tegrastats` during long conversations and while switching to coding. [Ollama memory guidance](https://docs.ollama.com/faq)

The runtime does not need PyTorch or a training environment. The setup script leaves power modes, swap, AppArmor, networking and desktop services unchanged. Optional console boot:

```bash
sudo systemctl set-default multi-user.target
# Restore desktop boot:
sudo systemctl set-default graphical.target
```

Use the board's supported power supply and cooling. The Orin Nano USB-C connector is for data, not power input. [NVIDIA hardware guide](https://docs.nvidia.com/jetson/orin-nano-devkit/user-guide/hardware_layout.html)

Remove the Ollama override with `sudo rm /etc/systemd/system/ollama.service.d/razaai-8g.conf`, then reload systemd and restart Ollama. This restores its previous settings.

## Workstation browser service

The RTX version offers an optional browser and API. Start it with `razaai web`, or install a user service:

```bash
scripts/install-service.sh standard
razaai token
```

Open `http://localhost:8420` and paste the token under Connection. The service installer creates `~/.config/razaai/server.env`. After editing settings:

```bash
systemctl --user restart razaai
journalctl --user -u razaai -f
# Stop it and disable startup:
systemctl --user disable --now razaai
```

User services start at login. To keep the service running after logout and start it at boot, enable lingering with `sudo loginctl enable-linger "$USER"`. Ollama must also start at boot.

For another computer, keep the API on loopback and use an SSH tunnel:

```bash
ssh -L 8420:127.0.0.1:8420 your-user@workstation-address
```

Open `http://localhost:8420` on that computer. The bearer token grants authority over the assistant and its configured tools. Plain HTTP does not encrypt it; use a tunnel or TLS for remote access. This is a single-operator service, not separate user accounts.

For a lightweight terminal client to the workstation service, run `./endpoint-install` from the source directory, set `RAZAAI_URL=http://localhost:8420` and `RAZAAI_TOKEN`, then run `raza`. That client only needs Python 3.8 or later.

## Backups and recovery

Back up the profile state under `~/.local/state/razaai` or `~/.local/state/razaai-8g`, private files under `config/` and `knowledge/local/`, and model weights you cannot download again. The vector index can be rebuilt from its reference documents.

`scripts/backup.sh backup` copies the default state locations and project data to a private backup directory. It respects `XDG_STATE_HOME`. If you override `RAZAAI_STATE_DIR`, back up that directory separately.

Use `razaai-8g doctor` to check the device. If memory is exhausted, stop competing workloads or unload an unused model with `ollama stop <model-tag>`.

## Incident learning

`razaai-8g learn` reviews validated incidents, updates confidence and refreshes the knowledge index. Run it after exiting the terminal, because the local vector store permits one process to open it at a time. Failures return a nonzero exit code.

Workstation service installation also creates a disabled `razaai-learning.timer`. Only enable it if you can keep indexing separate from active retrieval. The timer runs daily at 02:30 with a short random delay. Both profiles share the knowledge index by default, so use one learning process at a time.
