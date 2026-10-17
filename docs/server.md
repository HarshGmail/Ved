# Running Ved on a home server

From a fresh Ubuntu install to Ved running on the desktop, reachable from your
laptop and phone, and backed up. Written for the current home server: an Intel
i5, DDR3 RAM, three hard disks, no graphics card.

The corporate-network steps elsewhere in this repo (installing a company CA,
Colima) do not apply here. This machine runs Docker natively.

## The hardware, and what it means for the model

`sudo dmidecode -t memory` on this machine reports:

| | |
| --- | --- |
| Installed | 6 GB: one 4 GB and one 2 GB stick |
| Type | DDR3-1600, desktop DIMM, non-ECC |
| Slots | 2 |
| Board maximum | **16 GB** |

**Buy 2 × 8 GB DDR3-1600 desktop DIMMs** (240-pin, sold as PC3-12800, non-ECC)
and replace both sticks. A matched pair runs in dual-channel mode, which roughly
doubles memory bandwidth, and bandwidth is what limits a model on a CPU. Laptop
RAM (SO-DIMM) is a different size and won't fit.

**16 GB is the ceiling, so the Mac's model can't run here.** qwen3.6:35b needs
about 23 GB. Every word a model produces means reading its active weights from
RAM, and DDR3 is slow, so on this machine:

| Model | Size | Fits in 16 GB with Ved | Expect |
| --- | --- | --- | --- |
| `granite4.1:3b` | ~2 GB | yes | usable, slower than the Mac, weaker at tool calls |
| an 8B tool-capable model | ~5 GB | yes | noticeably slower; try it and judge |
| `qwen3.6:35b` | ~23 GB | no | — |

Start with `granite4.1:3b`. Check the CPU's vector support, which matters a lot
for speed:

```bash
lscpu | grep -oE 'avx2?' | sort -u
```

`avx2` in the output is good. Only `avx` means expect it to be slow.

**The model is the one part you can move later without changing code.** Ved
reaches it through `VED_LLM_BASE_URL`, so pointing that at a machine with a
graphics card, or a hosted endpoint, upgrades every answer at once. A used GPU
with 16–24 GB of memory is the upgrade that changes this machine the most.

### The disks

Three spinning disks and no SSD is fine at this scale. Postgres will be slower
than on an SSD, but Ved makes a few queries a minute.

- **Disk 1**: Ubuntu, Docker, and Postgres's data.
- **Disk 2**: backups. A backup on the same disk as the database dies with it.
- **Disk 3**: spare; later, the photo library or a mirror of disk 2.

## 1. Base system

```bash
sudo apt update && sudo apt full-upgrade -y
sudo apt install -y git curl ufw unattended-upgrades smartmontools
sudo dpkg-reconfigure -plow unattended-upgrades
```

The last line turns on automatic security updates.

## 2. Docker, uv, Node

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker "$USER"
curl -LsSf https://astral.sh/uv/install.sh | sh
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo bash - && sudo apt install -y nodejs
```

Log out and back in so the `docker` group applies, then check:

```bash
docker run --rm hello-world
```

## 3. Ollama

```bash
curl -fsSL https://ollama.com/install.sh | sh
sudo systemctl edit ollama
```

In the editor that opens, add:

```ini
[Service]
Environment="OLLAMA_FLASH_ATTENTION=1"
Environment="OLLAMA_KV_CACHE_TYPE=q8_0"
Environment="OLLAMA_KEEP_ALIVE=24h"
```

`OLLAMA_KEEP_ALIVE=24h` keeps the model loaded, so the first message after a
pause doesn't wait for it to load from a hard disk. `KV_CACHE_TYPE` must stay
at `q8_0`: lower values break tool calling.

```bash
sudo systemctl restart ollama
ollama pull granite4.1:3b
ollama pull nomic-embed-text
```

Ollama listens on `127.0.0.1:11434` only, which is what you want.

## 4. SSH with keys only

From the Mac, copy your key to the server:

```bash
ssh-copy-id you@<server-lan-ip>
```

Check you can log in without a password, then on the server:

```bash
echo "PasswordAuthentication no" | sudo tee /etc/ssh/sshd_config.d/no-passwords.conf
sudo systemctl restart ssh
```

Keep a session open while you do this, so a mistake can't lock you out.

## 5. Tailscale: reach it from anywhere

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up --ssh
```

Open the link it prints and sign in with the same account as your phone. In the
Tailscale admin console, under DNS, turn on **MagicDNS** and **HTTPS
Certificates**. Your server then has a name like `ved.<tailnet>.ts.net`, and
from any of your devices, anywhere:

```bash
ssh you@ved
```

No port is opened on your router. `--ssh` lets Tailscale handle SSH sign-in, so
you can also connect from the Tailscale app on your phone.

From the work laptop, GlobalProtect may block Tailscale. If it does, connect
from your personal laptop or phone instead.

## 6. Firewall

Allow SSH **before** enabling the firewall, or you'll lock yourself out:

```bash
sudo ufw allow OpenSSH
sudo ufw allow in on tailscale0
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw enable
sudo ufw status verbose
```

Everything in Ved binds to `127.0.0.1`, so nothing is reachable from the LAN
anyway. The firewall is the second layer.

## 7. Mount the backup disk

Find the disks and their UUIDs:

```bash
lsblk -f
```

If disk 2 has no filesystem yet (this erases it; double-check the name):

```bash
sudo mkfs.ext4 -L ved-backups /dev/sdX1
```

Mount it by UUID, so it survives the disks being renamed after a reboot:

```bash
sudo mkdir -p /srv/backups
echo "UUID=<uuid-from-lsblk> /srv/backups ext4 defaults,nofail 0 2" | sudo tee -a /etc/fstab
sudo mount -a && df -h /srv/backups
sudo chown "$USER":"$USER" /srv/backups
```

`nofail` means the server still boots if that disk dies.

## 8. Install Ved

```bash
git clone https://github.com/HarshGmail/Ved.git ~/Ved
cd ~/Ved
./ved setup
```

The first run creates the env files and stops to ask for a database password.
Set it in `infra/.env` and in `VED_DATABASE_URL` in `apps/backend/.env`, then
in `apps/backend/.env` also set the model this machine can run:

```bash
VED_LLM_MODEL=granite4.1:3b
```

Run `./ved setup` again. Then start Ved:

```bash
./ved db
./ved api       # in its own terminal
./ved web       # in its own terminal
```

Open `http://localhost:3000` on the server, or use the next step to open it from
your phone and laptop.

## 9. Use it from your phone and laptop

```bash
./ved phone
```

This serves Ved over Tailscale with real HTTPS, so install-to-home-screen and
push notifications work. Restart `./ved api` and `./ved web` after it, then open
the address it prints. Details: [phone-access.md](phone-access.md).

## 10. Disk health

The disks are the part most likely to fail. smartmontools watches them:

```bash
sudo smartctl -H /dev/sda          # repeat for each disk: PASSED is good
sudo systemctl enable --now smartd
```

Check every disk once now. A disk reporting reallocated or pending sectors is
on its way out; replace it before it takes data with it.

## 11. Power

A cheap UPS protects the database from being corrupted by a power cut, and
gives the disks a clean shutdown. With a USB-connected UPS, install `nut` to
shut the server down cleanly when the battery runs low.

## Still to come

Running Ved unattended — starting on boot, deploying automatically when CI
passes, and nightly backups to `/srv/backups` — is the next piece of work. Until
then, update by hand:

```bash
cd ~/Ved && git pull && ./ved setup && ./ved migrate
```

and restart `./ved api` and `./ved web`.

## Troubleshooting

| Symptom | Cause |
| --- | --- |
| `permission denied` from docker | Logged in before being added to the group. Log out and back in |
| `Docker is not running or not usable` | `sudo systemctl start docker`, then check the group membership above |
| Replies are very slow | Expected on CPU with DDR3. Check `avx2`, keep `OLLAMA_KEEP_ALIVE`, try a smaller model |
| The model calls tools badly or not at all | Small models are weaker at it. Try an 8B tool-capable model, or point `VED_LLM_BASE_URL` at a bigger one |
| `out of memory`, or Ollama crashes | The model doesn't fit. Use a smaller one, or stop `./ved studio` |
| Can't SSH after enabling the firewall | Connect at the machine and run `sudo ufw allow OpenSSH` |
| Backup disk missing after reboot | Check `/etc/fstab` uses the UUID and `nofail`, then `sudo mount -a` |
