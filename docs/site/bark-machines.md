# Bark machines

A **Bark machine** is an ordinary x86-64 computer that has stopped being a
computer and become a compute worker. There is no Linux underneath, no
hypervisor, no shell and no ssh: Bark boots from a USB stick or an internal
disk and *is* the machine. You send it tensor programs over HTTP; it runs them
and sends results back.

This page takes you from "I have the `bark-usb.img` file" to "my `.mnd` script
just ran on that laptop". It assumes nothing about the machine except that it
is x86-64 and you are allowed to reformat it.

> Installer downloads are not published yet. Until they are, the image comes
> from whoever built it for you, and this page starts from the moment you have
> it on disk.

## What Bark is

- A **bare-metal x86-64 compute worker**, written in freestanding C, with its own drivers, TCP/IP stack, HTTP server and tensor executor.
- About **191 KiB of kernel**. It boots in roughly **30 ms**.
- It speaks one protocol on two ports: **HTTP on 4780** for jobs, **UDP on 4781** for discovery.

```text
your laptop                          the machine running Bark
───────────                          ────────────────────────
maned-run  ──HTTP/TCP──►        USB Ethernet ─► TCP ─► HTTP ─► job queue
  .mnd file                                                        │
  compiled to MNPK bytes                                    tensor executor
  sent as a job                                                    │
            ◄──MNRS bytes──                                    results
```

And what it is **not**, because these shape everything below:

- **No operating system to log into.** The VGA screen and four keyboard keys are the entire local interface.
- **No remote install and no remote reconfiguration.** Provisioning happens at the machine, with a keyboard.
- **No wireless.** Networking is a USB Ethernet adapter or (under QEMU) a PCI RTL8139. A WiFi-only laptop cannot be a worker without a dongle.
- **No USB keyboard support.** The console driver is i8042/PS/2, scancode set 1. A built-in laptop keyboard is normally i8042-emulated; a plugged-in USB keyboard is not.

## How it works

**Boot.** GRUB loads the kernel into RAM, and after that the boot medium is
never touched again. Pull the stick out if you like — the worker keeps running.

**Identity.** Every worker has an `alias`, a `user` and a `pass`. They come from
three sources, in this order of precedence: the GRUB command line baked into the
image, an on-disk record written by a disk install, then an interactive prompt.
The on-disk record wins over the stick, which is exactly what makes a
disk-installed machine keep its own credentials no matter which stick you boot.

**Serving.** One main loop: poll the network, advance one job slice, repaint the
screen, `hlt` until the next interrupt. All packet processing happens on the
boot processor — **single-context by design**, a hard rule rather than a current
limitation. Jobs are asynchronous: submit, poll, fetch. Up to **four** queued,
results read-once with a 300-second expiry.

**Computing.** Programs arrive as a flat instruction stream over int32 tensors.
Arithmetic wraps mod 2³² deliberately, so results are bit-exact and reproducible
however the work is split. Long operations suspend and resume, so the status
endpoint still answers in under a second in the middle of a matmul. Matmul can
spread its rows across CPU cores; everything else runs on one.

## What you need

| | Why |
|---|---|
| The `bark-usb.img` file | The image you were given. It boots BIOS/CSM **and** UEFI firmware — one hybrid image, no variants to choose between. |
| A USB stick | Anything that fits the image. Its previous contents are gone. |
| The target machine | x86-64, with a keyboard the firmware presents as PS/2. Laptops usually qualify; a desktop with only USB ports for the keyboard may not. |
| **A USB Ethernet adapter** | Not optional on real hardware. An RTL8153-class adapter presenting CDC-ECM is the tested one. |
| A cable and a port that gives out DHCP leases | Without a lease the worker runs but nothing finds it. |
| A camera or phone | See [Reading the screen](#first-boot-reading-the-screen) — the on-screen log keeps 20 lines and there is no scrollback. |

## Write the image to a stick

**macOS** — find the disk, unmount it, write to the *raw* device (`rdiskN` is
far faster than `diskN`):

```sh
diskutil list
diskutil unmountDisk /dev/diskN
sudo dd if=bark-usb.img of=/dev/rdiskN bs=4m conv=fsync
```

**Linux**:

```sh
lsblk
sudo umount /dev/sdX*        # any auto-mounted partitions
sudo dd if=bark-usb.img of=/dev/sdX bs=4M conv=fsync status=progress
```

Check `N` / `X` twice. `dd` will happily overwrite the wrong disk.

**Treat the stick as a written-down password.** Unless your image was built
without baked credentials, the worker's password sits in plaintext in
`/boot/grub/grub.cfg` inside the image, and anyone who mounts the stick on any
computer can read it. Do not lend an install stick to someone you would not
give the credentials to, and do not leave one in a machine you walk away from.
An image built in setup mode carries no credentials at all and asks the machine
for its own identity at first boot — that is the one to hand over.

## Firmware settings, before you boot

Settle these in the firmware setup screen first. Each one can cost you a trip.

| Setting | Value | Why |
|---|---|---|
| Secure Boot | **off** | GRUB and the kernel are unsigned. |
| SATA mode | **AHCI**, not RAID / Intel RST | In RST mode the controller answers as PCI class `01:04`, Bark's probe looks for `01:06`, and the machine boots with **no disk at all** — no persistence, no install target. |
| Boot order | **USB first** | Then inserting the stick is always the escape hatch on a machine whose disk install is broken. It costs nothing and there is no in-band way to recover a machine that prefers a broken internal disk. |
| CSM / legacy boot | on, if the machine offers it | UEFI works and is bench-verified, but CSM is the path with hardware miles on it. |

⚠ **Switching an installed Windows from RST to AHCI makes that Windows
unbootable.** If this machine is meant to demonstrate that removing Bark
restores its original system, decide that before touching the SATA mode.

## First boot: reading the screen

Insert the stick, power on, and Bark paints a status faceplate:

```text
┌─[ IDENTITY ]──────────────────┬─[ RESOURCES ]──────────────────┐
│ alias    rex                  │ heap    ▓▓▓░░░░░░░  28%        │
│ user     maned                │ memory  ▓░░░░░░░░░  11%        │
│ ip       10.0.0.21            │                                │
│ status   READY                │ NODE ──────────────────────    │
│                               │ cpu     Intel(R) Core(TM) ...  │
│                               │         2.60 GHz · 4 cpus      │
├─[ OPERATIONS ]────────────────┴────────────────────────────────┤
│ matmul add sub mul div relu transpose scalar_mul ...           │
├────────────────────────────────────────────────────────────────┤
│ [R] reboot   [P] setup   [I] disk   [L] log      4780 · 4781   │
└────────────────────────────────────────────────────────────────┘
```

(A sketch of the layout, with placeholder values — the panels, the field
names and the footer are what the worker actually draws.)

`status` reads `READY` or `SERVING (n)`. The two numbers in the footer are the
HTTP and discovery ports.

### Press `[L]` first

`[L]` toggles between the status page and the kernel log. It changes nothing and
touches no disk, which makes it a zero-risk proof that the keyboard is being
read — **before** you confirm anything destructive. If `[L]` does not page, stop:
the keyboard is not delivering keys, and no confirmation word you type later
will register either.

**Then photograph the log page immediately.** The ring holds **20 lines** and
there is no scrollback. Once the network comes up, DHCP, ARP and HTTP traffic
push the boot lines out within seconds. The page header tells you whether you
were fast enough: `20 of 20 lines kept` means it has already wrapped and the
boot-time lines are gone for the life of this boot.

### The four keys

| Key | Does | Notes |
|---|---|---|
| `[L]` | status ⇄ kernel log | Zero risk. The keyboard proof. |
| `[R]` | reboot | Confirmed by typing the word `reboot`. |
| `[P]` | change alias / user / password | Dims to `locked` for 60 s after three wrong passwords. |
| `[I]` | install to disk / update / remove | Dims when there is no disk to install to. |

All four are non-blocking page states — the worker keeps serving jobs while you
are on any of them. Key dispatch is page-scoped: inside `[I]`, `[P]` or `[R]`
every key is text, so `[L]` will not page away in the middle of a confirmation
word. Back out first to read the log.

### A healthy boot

Good signs, in order — disk first, then whichever NIC this machine has:

```text
PCI-AHCI: FOUND → AHCI-DISK: <model> <n> sectors → BOOTDISK: <i>/<n> <reason>
→ IDENT-DISK: LOADED (or CMDLINE)
→ PCI-XHCI: FOUND → XHCI: PASS → USB-ENUM: … → USB-CONFIG: cfg=2 ecm-nic
→ USB-NIC: UP <mac> → USB-NIC-TX: PASS
→ DHCP: PASS → ARP-RESOLVE: PASS → HTTP-LISTEN: PASS → DISCOVERY-LISTEN: PASS
→ BOOT-COMPLETE
```

Two lines people misread on real hardware:

- **`LINK: PASS` never appears** on a USB-dongle machine. That line belongs to the PCI RTL8139 path, which is the QEMU one. Judge the network by `USB-NIC-TX: PASS` and `DHCP: PASS` instead.
- **`PCI-RTL8139: NOT-FOUND` is expected.** A laptop has no RTL8139. It is not a failure and needs no action.

`DHCP: FALLBACK` instead of `PASS` means no lease was offered: the worker still
runs, on a static fallback address, but nothing on your network will find it.
Check the cable and the switch port.

## Setting the machine's identity

If your image was built in setup mode, the machine asks for its alias, user and
password at first boot — nothing was baked in, and that is the safest way to
receive an image from someone else.

Otherwise the image's credentials are in force, and you should change them at
the machine with `[P]`. Three wrong attempts at the current password lock the
key for 60 seconds.

**A password you set with `[P]` only survives a reboot if the machine has a disk
install** — otherwise the identity lives in RAM and the stick's credentials come
back on the next boot. That is the first reason to install to disk.

If a machine's stored password is ever lost, the recovery is a stick whose
command line carries the bare token `nodisk`: it ignores the on-disk identity
for that one boot so you can `[P]` a new one. That stick has to be built in
advance — the boot menu has a zero timeout and there is no GRUB prompt to type
it at.

## Stick or disk?

A worker running from the stick is a complete worker. Installing to disk buys
three things:

| | From the stick | Installed to disk |
|---|---|---|
| Credentials set with `[P]` | lost on reboot | persist |
| Boots without the stick | no | yes |
| Survives a power cut unattended | no | yes — comes back a worker with nobody present |

For a machine that lives on a shelf and serves jobs, install it. For trying Bark
out on a laptop you want back, run from the stick and take it with you.

### What the `[I]` page shows

The page surveys the disk when you enter it, and again after every action, so it
is the one piece of state that is still true an hour later:

```text
disk       <model> · <N> MiB · boot: usb|disk
table      GPT · N partitions   |   no GPT · unpartitioned or MBR
bark       not installed | identity partition only | system installed
installed  <version> or -
this stick <version> or "carries no system to install"
```

Record this block before you act. It names the disk model, or gives the reason
there is none.

### The options, and their confirmation words

Each action has **its own word**, so muscle-memory typing of one word cannot
confirm a different action. On a disk with no Bark on it:

| | Option | Word | What it does |
|---|---|---|---|
| `[1]` | install system — whole disk | `replace` | Writes Bark's own partition table. Existing partitions become unreachable. |
| `[2]` | install system — free space | `install` | Claims only unallocated space. Existing partitions are preserved, and `remove` later restores the previous boot code. |
| `[3]` | identity only — free space | `identity` | 1 MiB for credentials. The machine keeps booting from the stick. |

On a disk that already carries Bark, the same two keys mean `update` (write this
stick's system over the installed one, leaving credentials and the partition
table untouched) and `remove`.

Three behaviours worth knowing:

- **The word "erase" never appears on this page**, by rule. If you see it, that is a defect worth reporting.
- **Anything unoffered backs out.** On the menu, any key that is not a live option returns to the status page. That is the cancel.
- **On a confirmation, Enter on anything but the exact word cancels.**

Free-space install needs a GPT disk — an MBR disk has no table to add to, so
`[2]` and `[3]` are dimmed and only the whole-disk install is offered. Bark
never shrinks, moves or resizes an existing partition: it claims space that is
already free, or nothing. Make room with the other system's own tools first.

### After the install

1. `[I]` again. `bark` must read `system installed` with **no** `NOT bootable` clause. If that clause is there, the install died between its two commit points — **re-running the install is the designed repair**, not a workaround.
2. Remove the stick and power-cycle. Pick the internal disk in the firmware boot menu if it does not come up on its own.
3. The status page should show `boot: disk`, and the log `IDENT-DISK: LOADED`.

NVMe is honest but two-sided: persistence and install work, but *booting* also
needs the firmware to expose the namespace, and some BIOS/CSM machines do not.
**Install, then verify by booting once.** A namespace with 4096-byte sectors is
reported and then refused by name; the machine still boots, using the stick's
identity, but it cannot be an install target.

## Connect it to Maned

Bark answers a UDP broadcast probe on port 4781, so a worker on your LAN
announces itself without configuration:

```text
$ maned-run devices
ALIAS    KIND  ADDRESS            BUSY  OPS
rex      x86   10.0.0.21:4780     no    matmul,add,sub,mul,div,relu,transpose,...
bob      x86   10.0.0.22:4780     no    matmul,add,sub,mul,div,relu,transpose,...
```

If broadcast does not cross your network, probe directly:

```sh
maned-run devices --probe 10.0.0.21:4780 --timeout 1000
```

Then name it in a script and send it work:

```mnd
mnd::quantmax=1000;
mnd::quantmin=-1000;
mnd::quantres=0;

in::a = [[1,2],[3,4]];
in::b = [[5,6],[7,8]];

device::rex {
    host = "10.0.0.21";
    port = 4780;
    user = "maned";
    pass = env("BARK_PASS");
}

calc::lambda_flow mm(a, b) @device(rex) {
    a b matmul r =
} return r;
```

```text
$ BARK_PASS=... maned-run hello.mnd --verify
flow 'mm' outputs:
r : [2x2] = [19, 22, 43, 50]
verify: PASS (compared local interpreter vs routed targets)
```

`--verify` re-runs the same plan on the local interpreter and compares every
decoded remote output exactly. Use it on a machine's first job: it is the
difference between "the worker answered" and "the worker answered correctly".

`env("NAME")` is resolved at run time and never appears in a diagnostic. A
literal `pass = "..."` works and the linter warns about it every time.

### What the coordinator checks before sending work

Every worker answers `GET /api/status`, and `maned-run` reads it before
dispatching:

```json
{"proto":1,"alias":"bob","kind":"x86","uptime_s":170053,"requests":180,
 "jobs_running":0,"jobs_capacity":4,
 "ops":["matmul","add","sub","mul","div","relu","transpose", ...],
 "max_payload":33554432,"ir":2,"rf_slots":4096}
```

- **`ops`** is the capability check. A flow using an operation this worker does not advertise is refused in the pre-flight, not half way through.
- **`ir` and `rf_slots`** are the instruction-set ABI and the register budget. `rf_slots: 4096` is an ABI v2 worker; an older one reports 256, and `calc::ml::` takes `budget: 256` to size its round chunks for it.
- **`max_payload`** caps one request. `jobs_capacity` is how many jobs can queue.

From here, [Remote workers](guides/remote-workers.html) covers routing in
general, and [Training across Bark devices](guides/ml-parallel.html) covers
spreading model training over several of them.

## When something is wrong

The string on the screen *is* the diagnosis. The ones you can act on:

| String | Means | Do |
|---|---|---|
| `AHCI: NOT-FOUND` | Firmware is in RAID/RST mode — **or** this machine simply has no AHCI controller, which is normal for NVMe-only | Check the SATA mode first. If it is already AHCI, look for `NVME-DISK:` in the same log |
| `AHCI: NO-DISK` | The controller was found; no port survived bring-up | Photograph the log — the reason line below it is the real finding |
| `BOOTDISK: NONE (cannot tell which disk is ours - refusing to guess)` | More than one disk carries Bark | Remove the extra Bark disk. The kernel binds to nothing rather than guess |
| `system installed · NOT bootable: re-run the install` | The install died before writing LBA 0 | Re-run the install. That is the repair |
| `this stick carries no system to install` | The image has no install payload | Nothing to do at the machine — you need a different image |
| `USB-ENUM: no CDC-ECM adapter found` | Dongle absent, on a port that did not enumerate, or in the wrong configuration | Reseat it and try other ports |
| `DHCP: FALLBACK` | No lease | Check the cable and the switch port |
| `[P]` shows `locked` | Three wrong passwords | Wait 60 seconds |

If the machine will not boot from its disk at all, insert the stick. That is
what "USB first in the boot order" is for.

## Known limits, stated plainly

- **No wireless.** USB CDC-ECM or (QEMU) PCI RTL8139 only.
- **No USB keyboard.** PS/2 / i8042 only, and there is no workaround at the machine.
- **No remote install.** Provisioning is done at the machine's own screen.
- **The password is plaintext on the stick**, unless the image was built in setup mode.
- **No shrinking, moving or resizing** an existing partition, ever.
- **4096-byte-sector NVMe cannot be an install target.** The machine still boots and still works.
- **A machine with both AHCI and NVMe disks**: the first controller found wins.
- **UEFI boot is bench-verified, not yet hardware-verified.** Treat a first CSM-less machine as a bring-up rather than a deployment; if the machine offers CSM, that is the path with hardware miles on it.

## Next

- [Remote workers](guides/remote-workers.html) — routing flows, async slots, dependency chains, and the Bark VM for when you have no hardware yet.
- [Training across Bark devices](guides/ml-parallel.html) — spreading `calc::ml::` training over a fleet.
- [How Maned runs your program](under-the-hood.html) — what happens between `maned-run` and a result.
